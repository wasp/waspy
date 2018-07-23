import asyncio
import traceback
import logging
import urllib.parse
from http import HTTPStatus

from httptools import HttpRequestParser, HttpResponseParser, HttpParserError, \
        parse_url

from ..webtypes import Request, Response
from .transportabc import TransportABC, ClientTransportABC

logger = logging.getLogger('waspy')


class ClosedError(Exception):
    """ Error for closed connections """


class _HTTPClientConnection:
    slots = ('reader', 'writer', 'http_parser', '_done', '_data')

    def __init__(self):
        self.reader = None
        self.writer = None
        self.http_parser = HttpResponseParser(self)
        self.response = None
        self._data = b''
        self._done = False

    async def connect(self, service, port, use_ssl):
        for _ in range(3):
            try:
                self.reader, self.writer = await \
                    asyncio.open_connection(service, port, ssl=use_ssl)
                return
            except ConnectionRefusedError:
                """ connection refused. Try again """
        raise ConnectionRefusedError(
            f'Connection refused to "{service}" on port {port}')

    def send(self, method, path, headers, body):
        self.writer.write(f'{method.upper()} {path} HTTP/1.0\r\n'
                          .encode('latin-1'))
        for header, value in headers:
            self.writer.write(f'{header}: {value}\r\n'.encode('latin-1'))
        self.writer.write(b'\r\n')
        if body:
            self.writer.write(body)

    async def get_response(self):
        while True:
            data = await self.reader.read(1064)
            self.http_parser.feed_data(data)
            if self._done:
                return self.response

    def close(self):
        self.writer.close()

    """ http parsing methods below """

    def on_message_begin(self):
        self.response = Response()

    def on_header(self, name, value):
        name = name.decode('latin-1')
        value = value.decode()
        if name == 'X-Correlation-ID':
            self.response.correlation_id = value
        elif name.lower() == 'content-type':
            self.response.content_type = value
        else:
            self.response.headers[name] = value

    def on_headers_complete(self):
        self.response.status = HTTPStatus(self.http_parser.get_status_code())

    def on_body(self, body):
        self._data += body

    def on_message_complete(self):
        self.response.body = self._data
        self._data = b''
        self._done = True


class HTTPClientTransport(ClientTransportABC):
    """Client implementation of the HTTP transport protocol"""

    def _get_connection_for_service(self, service):
        pass

    async def make_request(self,
                           service,
                           method,
                           path,
                           body=None,
                           query=None,
                           headers=None,
                           correlation_id=None,
                           content_type=None,
                           port=80,
                           **kwargs):
        # form request object
        if not path.startswith('/'):
            path = '/' + path
        path = path.replace(' ', '+')
        if headers is None:
            headers = {}
        use_ssl = service.startswith('https://') or port == 443
        if service.startswith('http'):
            service = service.replace('http://', '').replace('https://', '')
        if use_ssl and port == 80:
            port = 443
        if 'Host' not in headers and 'host' not in headers:
            headers['Host'] = service
            if port not in (80, 443):
                headers['Host'] += ':{}'.format(port)
        headers['Connection'] = 'close'
        headers.pop('connection', None)
        if correlation_id:
            headers['X-Correlation-Id'] = correlation_id
        if query:
            path += '?' + query
        if content_type:
            if body:  # dont include content-type if there is no body
                headers['Content-Type'] = content_type
        headers.pop('content-type', None)
        headers.pop('content-length', None)
        headers.pop('Content-Length', None)
        if body:
            headers['Content-Length'] = str(len(body))
        headers['User-Agent'] = headers.pop('user-agent', 'waspy-http-client')

        # now make a connection and send it
        connection = _HTTPClientConnection()
        await connection.connect(service, port, use_ssl)
        connection.send(method, path, headers.items(), body)
        try:
            result = await connection.get_response()
        finally:
            connection.close()
        return result


class HTTPTransport(TransportABC):
    """ Server implementation of the HTTP transport protocol"""

    def get_client(self):
        return HTTPClientTransport()

    def __init__(self,
                 port=8080,
                 prefix=None,
                 shutdown_grace_period=5,
                 shutdown_wait_period=1):
        """
         HTTP Transport for listening on http
         :param port: The port to lisen on (0.0.0.0 will always be used)
         :param prefix: the path prefix to remove from all url's
         :param shutdown_grace_period: Time to wait for server to shutdown
         before connections get forceably closed. The only way for connections
         to not be forcibly closed is to have some connection draining in front
         of the service for deploys. Most docker schedulers will do this for you.
         :param shutdown_wait_period: Time to wait after recieving the sigterm
         before starting shutdown 
         """
        self.port = port
        if prefix is None:
            prefix = ''
        self.prefix = prefix
        self._handler = None
        self._server = None
        self._loop = None
        self._done_future = asyncio.Future()
        self._connections = set()
        self.shutdown_grace_period = shutdown_grace_period
        self.shutdown_wait_period = shutdown_wait_period
        self.shutting_down = False
        self._config = {}

    def listen(self, *, loop: asyncio.AbstractEventLoop, config):
        self._loop = loop
        self._config = config
        if self._config['debug']:
            self.shutdown_grace_period = 0
            self.shutdown_wait_period = 0
            self._debug = True

    async def start(self, request_handler):
        self._handler = request_handler
        self._server = await self._loop.create_server(
            lambda: _HTTPServerProtocol(parent=self, loop=self._loop),
            host='0.0.0.0',
            port=self.port,
            reuse_address=True)
        print(f'-- Listening for HTTP on port {self.port} --')
        try:
            await self._done_future
        except asyncio.CancelledError:
            pass

        logger.warning("Shutting down HTTP transport")
        await asyncio.sleep(self.shutdown_wait_period)
        # wait for connections to stop
        times_no_connections = 0
        for _ in range(self.shutdown_grace_period):
            if not self._connections:
                times_no_connections += 1
            else:
                times_no_connections = 0
                for con in self._connections:
                    con.attempt_close()

            if times_no_connections > 3:
                # three seconds with no connections
                break
            await asyncio.sleep(1)

        # Shut the server down
        self._server.close()
        await self._server.wait_closed()

    async def handle_incoming_request(self, request):
        logger.debug('received incoming request via http: %s', request)
        response = await self._handler(request)
        return response

    def shutdown(self):
        self.shutting_down = True
        self._done_future.cancel()


class _HTTPServerProtocol(asyncio.Protocol):
    """ HTTP Protocol handler.
        Should only be used by HTTPServerTransport
    """
    __slots__ = ('_parent', '_transport', '_task', 'data', 'http_parser',
                 'request')

    def __init__(self, *, parent, loop):
        self._parent = parent
        self._transport = None
        self.data = None
        self.http_parser = HttpRequestParser(self)
        self.request = None
        self._loop = loop
        self._task: asyncio.Task = None

    """ The next 3 methods are for asyncio.Protocol handling """

    def connection_made(self, transport):
        self._transport = transport
        self._parent._connections.add(self)

    def connection_lost(self, exc):
        self._parent._connections.discard(self)
        if self._task:
            self._task.cancel()
        self._transport = None

    def data_received(self, data):
        try:
            self.http_parser.feed_data(data)
        except HttpParserError as e:
            traceback.print_exc()
            logger.error('Bad http: %s', self.request)
            if self._transport:
                self.send_response(
                    Response(
                        status=400,
                        body={
                            'reason': 'Invalid HTTP',
                            'details': str(e)
                        }))

    """ 
    The following methods are for HTTP parsing (from httptools)
    """

    def on_message_begin(self):
        self.request = Request()
        self.data = b''

    def on_header(self, name, value):
        key = name.decode('latin-1').lower()
        if not value:
            value = b''

        val = value.decode()
        self.request.headers[key] = val
        if key == 'x-correlation-id':
            self.request.correlation_id = val
        if key == 'content-type':
            self.request.content_type = val

    def on_headers_complete(self):
        self.request.method = self.http_parser.get_method().decode('latin-1')

    def on_body(self, body: bytes):
        self.data += body

    def on_message_complete(self):
        self.request.body = self.data
        task = self._loop.create_task(
            self._parent.handle_incoming_request(self.request))
        task.add_done_callback(self.handle_response)
        self._task = task

    def on_url(self, url):
        url = url.replace(b'//', b'/')
        url = parse_url(url)
        if url.query:
            # query = urllib.parse.unquote(url.query.decode('latin-1'))
            self.request.query_string = url.query.decode('latin-1')
        path = urllib.parse.unquote(url.path.decode('latin-1'))
        if path.startswith(self._parent.prefix):
            path = path[len(self._parent.prefix):]
        self.request.path = path

    """
    End parsing methods
    """

    def handle_response(self, future):
        try:
            self.send_response(future.result())
        except Exception:
            traceback.print_exc()
            self.send_response(
                Response(
                    status=500,
                    body={'reason': 'Something really bad happened'},
                    content_type=self.request.app.default_content_type
                ))

    def send_response(self, response):
        if response is None:
            # connection closed, no response
            return

        headers = 'HTTP/1.1 {status_code} {status_message}\r\n'.format(
            status_code=response.status.value,
            status_message=response.status.phrase,
        )
        headers += 'Connection: close\r\n'
        # if self._parent.shutting_down:
            # headers += 'Connection: close\r\n'
        # else:
            # headers += 'Connection: keep-alive\r\n'
            # headers += 'Keep-Alive: timeout=5, max=50\r\n'

        if response.raw_body:
            headers += 'Content-Type: {}\r\n'.format(response.content_type)
            headers += 'Content-Length: {}\r\n'.format(len(response.raw_body))
            if ('transfer-encoding' in response.headers
                    or 'Transfer-Encoding' in response.headers):
                print('Httptoolstransport currently doesnt support '
                      'chunked mode, attempting without.')
                response.headers.pop('transfer-encoding', None)
                response.headers.pop('Transfer-Encoding', None)
        else:
            headers += 'Content-Length: {}\r\n'.format(0)
        for header, value in response.headers.items():
            if header in ('Content-Length', 'content-lenth'):
                continue
            headers += '{header}: {value}\r\n'.format(
                header=header, value=value)

        result = headers.encode('latin-1') + b'\r\n'
        if response.raw_body:
            result += response.raw_body

        try:
            self._transport.write(result)
        except AttributeError:
            # "NoneType has no attribute 'write'" because transport is closed
            logger.debug(
                'Connection closed prematurely, most likely by client')
        self.request = 0
        self.data = 0
        self.attempt_close()

    def attempt_close(self):
        if self.request == 0 and self._transport:
            self._transport.close()
