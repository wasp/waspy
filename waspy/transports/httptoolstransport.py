"""
This is a rewrite of the HTTP transport to use httptools parser
It currently still uses h11 for client transport
"""

import asyncio
import socket

import h11
try:
    from httptools import HttpRequestParser, HttpResponseParser, HttpParserError, \
        parse_url
except ImportError:
    pass  # You need to have httptools installed to use this

from ..webtypes import Request, Response
from .transportabc import TransportABC, ClientTransportABC


class ClosedError(Exception):
    """ Error for closed connections """


class _HTTPClientConnection:
    slots = ('reader', 'writer', 'conn', 'port', 'service')

    def __init__(self, service, port):
        self.reader = None
        self.writer = None
        self.port = port
        self.service = service
        self.conn = h11.Connection(our_role=h11.CLIENT)

    async def connect(self):
        self.reader, self.writer = await \
            asyncio.open_connection(self.service, self.port)

    def send(self, event):
        data = self.conn.send(event)
        if data is not None:
            self.writer.write(data)

    async def next_event(self):
        while True:
            event = self.conn.next_event()
            if event is h11.NEED_DATA:
                data = await self.reader.read(1064)
                self.conn.receive_data(data)

            else:
                return event

    def close(self):
        self.send(h11.ConnectionClosed())
        self.writer.close()


class HTTPClientTransport(ClientTransportABC):
    """Client implementation of the HTTP transport protocol"""
    def _get_connection_for_service(self, service):
        pass

    async def make_request(self, service, method, path, body=None, query=None,
                           headers=None, correlation_id=None,
                           content_type=None, port=80, **kwargs):
        # form request object
        path = path.replace('.', '/')
        if headers is None:
            headers = {}
        headers['Host'] = service
        headers['Connection'] = 'close'
        if correlation_id:
            headers['X-Correlation-Id'] = correlation_id
        if query:
            path += '?' + query
        if content_type:
            headers['Content-Type'] = content_type
        if body:
            headers['Content-Length'] = str(len(body))

        # now make a connection and send it
        connection = _HTTPClientConnection(service, port)
        await connection.connect()
        connection.send(h11.Request(method=method, target=path,
                                    headers=headers.items()))
        if body:
            connection.send(h11.Data(data=body))

        connection.send(h11.EndOfMessage())

        response = await connection.next_event()
        assert type(response) is h11.Response

        # form response object

        status_code = response.status_code
        headers = response.headers

        result = Response(headers=headers, correlation_id=correlation_id,
                          status=status_code)

        body = b''
        event = None
        while type(event) is not h11.EndOfMessage:
            event = await connection.next_event()
            if type(event) is h11.Data:
                body += body

        result.body = body
        connection.close()
        return result


class HTTPTransport(TransportABC):
    """ Server implementation of the HTTP transport protocol"""

    def get_client(self):
        return HTTPClientTransport()

    def __init__(self, port=8080, prefix=None, shutdown_grace_period=5):
        """
         HTTP Transport for listening on http
         :param port: The port to lisen on (0.0.0.0 will always be used)
         :param prefix: the path prefix to remove from all url's
         :param shutdown_grace_period: Time to wait for server to shutdown
         before connections get forceably closed. The only way for connections
         to not be forcibly closed is to have some connection draining in front
         of the service for deploys. Most docker schedulers will do this for you.
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

    def listen(self, *, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def start(self, request_handler):
        self._handler = request_handler
        self._server = await self._loop.create_server(
            lambda: _HTTPServerProtocol(parent=self, loop=self._loop),
            host='0.0.0.0',
            port=self.port,
            reuse_address=True,
            reuse_port=True)
        print('-- Listening for HTTP on port {} --'.format(self.port))
        try:
            await self._done_future
        except asyncio.CancelledError:
            pass
        print('shutting down http')

        # wait for connections to stop
        for i in range(self.shutdown_grace_period):
            for con in self._connections:
                con.attempt_close()
            if not self._connections:
                break
            await asyncio.sleep(1)

        # Shut the server down
        self._server.close()
        await self._server.wait_closed()

    async def handle_incoming_request(self, request):
        response = await self._handler(request)
        return response

    def shutdown(self):
        self._server.close()
        self._done_future.cancel()


class _HTTPServerProtocol(asyncio.Protocol):
    """ HTTP Protocol handler.
        Should only be used by HTTPServerTransport
    """
    __slots__ = ('_parent', '_transport', 'data', 'http_parser',
                 'request')

    def __init__(self, *, parent, loop):
        self._parent = parent
        self._transport = None
        self.data = None
        self.http_parser = HttpRequestParser(self)
        self.request = None
        self._loop = loop

    """ The next 3 methods are for asyncio.Protocol handling """
    def connection_made(self, transport):
        self._transport = transport
        self._parent._connections.add(self)

    def connection_lost(self, exc):
        self._parent._connections.discard(self)

    def data_received(self, data):
        try:
            self.http_parser.feed_data(data)
        except HttpParserError as e:
            self.send_response(Response(status=400,
                                        body={'reason': 'Invalid HTTP'}))

    """ 
    The following methods are for HTTP parsing (from httptools)
    """
    def on_message_begin(self):
        self.request = Request()
        self.data = b''

    def on_header(self, name, value):
        key = name.decode('ASCII').lower()
        val = value.decode()
        self.request.headers[key] = val
        if key == 'x-correlation-id':
            self.request.correlation_id = val
        if key == 'content-type':
            self.request.content_type = val

    def on_headers_complete(self):
        self.request.method = self.http_parser.get_method().decode('ASCII')

    def on_body(self, body: bytes):
        self.data += body

    def on_message_complete(self):
        self.request.body = self.data
        task = self._loop.create_task(
            self._parent.handle_incoming_request(self.request)
        )
        task.add_done_callback(self.handle_response)

    def on_url(self, url):
        url = parse_url(url)
        if url.query:
            self.request.query_string = url.query.decode('ASCII')
        self.request.path = url.path.decode('ASCII')

    """
    End parsing methods
    """

    def handle_response(self, future):
        try:
            self.send_response(future.result())
        except Exception:
            self.send_response(
                Response(status=500,
                         body={'reason': 'Something really bad happened'}))

    def send_response(self, response):
        try:
            content_length = len(response.data)
        except TypeError:
            content_length = 0
        headers = '''\
HTTP/1.1 {status_code} {status_message}\r
Connection: keep-alive\r
Content-Length: {content_length}\r
'''.format(status_code=response.status.value,
           status_message=response.status.phrase,
           content_length=content_length,
           )
        if response.body:
            headers += 'Content-Type: {}\r\n'.format(response.content_type)
        for header, value in response.headers.items():
            headers += '{header}: {value}\r\n'.format(header=header,
                                                      value=value)

        result = headers.encode('ASCII') + b'\r\n'
        if response.body:
            result += response.data

        self._transport.write(result)
        self.request = 0
        self.data = 0

    def attempt_close(self):
        if self.request == 0:
            self._transport.close()
