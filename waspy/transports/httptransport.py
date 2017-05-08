import asyncio
import socket

import h11

from ..webtypes import Request, Response, ResponseError
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
        try:
            self.reader, self.writer = await \
                asyncio.open_connection(self.service, self.port)
        except socket.gaierror as e:
            raise ResponseError(e.strerror,
                                reason='Can not connect to service {service}.'
                                       .format(service=self.service),
                                status=503)

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
            headers['X-Correlation-Id'] = str(correlation_id)
        if query:
            path += '?' + query
        if content_type:
            headers['Content-Type'] = content_type
        if body:
            headers['Content-Length'] = str(len(body))
        else:
            headers['Content-Length'] = '0'

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
        headers = {name.decode('ascii'): value.decode('ascii')
                   for name, value in response.headers}

        result = Response(headers=headers, correlation_id=correlation_id,
                          status=status_code)

        body = b''
        event = None
        while type(event) is not h11.EndOfMessage:
            event = await connection.next_event()
            if type(event) is h11.Data:
                body += event.data

        result.body = body
        connection.close()
        return result


class HTTPTransport(TransportABC):
    """ Server implementation of the HTTP transport protocol"""

    def get_client(self):
        return HTTPClientTransport()

    def __init__(self, port=8080, prefix=None, shutdown_grace_period=15):
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
        self.shutdown_grace_period = shutdown_grace_period
        self._handler = None
        self._server = None
        self._done_future = asyncio.Future()
        self._count = 0
        self._shutting_down = False
        self._sleeping_connections = set()

    def listen(self, *, loop: asyncio.AbstractEventLoop):
        coro = asyncio.start_server(
            self.handle_incoming_request, '0.0.0.0', self.port, loop=loop)
        self._server = loop.run_until_complete(coro)
        print('-- Listening for HTTP on port {} --'.format(self.port))

    async def start(self, request_handler):
        self._handler = request_handler
        try:
            await self._done_future
        except asyncio.CancelledError:
            pass

        # Enter shutdown step

        print('shutting down http')
        self._shutting_down = True
        for coro in self._sleeping_connections:
            coro.cancel()

        # we should wait some time for connections to stop
        previous_count = self._count
        for i in range(self.shutdown_grace_period):
            await asyncio.sleep(1)
            if self._count == previous_count:
                # no more connections
                break
            else:
                previous_count = self._count

        self._server.close()
        await self._server.wait_closed()

    async def handle_incoming_request(self, reader, writer):
        if self._shutting_down:
            self._count += 1
        self._set_tcp_nodelay(writer)
        protocol = _HTTPServerProtocol(reader=reader, writer=writer,
                                       prefix=self.prefix)
        try:
            while True:
                inner = asyncio.Task(protocol.get_request())
                coro = asyncio.shield(inner)
                self._sleeping_connections.add(coro)
                try:
                    request = await coro
                except asyncio.CancelledError:
                    # Give the request a chance to send a request if it has one
                    if inner.done():
                        request = inner.result()
                    else:
                        request = await asyncio.wait_for(inner, 1)
                self._sleeping_connections.remove(coro)
                response = await self._handler(request)
                await protocol.send_response(response)
                if protocol.conn.our_state is h11.MUST_CLOSE:
                    break
                if self._shutting_down:
                    break
                protocol.conn.start_next_cycle()
        except (ClosedError, ConnectionResetError,
                asyncio.CancelledError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()

    def shutdown(self):
        self._done_future.cancel()

    def _set_tcp_nodelay(self, writer):
        socket_ = writer._transport._sock
        if socket_ is None:
            return
        if socket_.family not in (socket.AF_INET, socket.AF_INET6):
            return
        socket_.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)


class _HTTPServerProtocol(asyncio.Protocol):
    """ HTTP Protocol handler.
        Should only be used by HTTPServerTransport
    """
    __slots__ = ('conn', 'reader', 'writer')

    def __init__(self, reader=None, writer=None, prefix=None):
        self.conn = h11.Connection(h11.SERVER)
        self.reader = reader
        self.writer = writer
        self.prefix = prefix

    async def _read(self):
        if self.conn.they_are_waiting_for_100_continue:
            go_ahead = h11.InformationalResponse(status_code=100)
            await self.writer.write(go_ahead)
        try:
            data = await self.reader.read(1000000)
        except ConnectionError:
            data = b''
        self.conn.receive_data(data)

    async def send_response(self, response: Response):
        headers = response.headers
        if response.content_type:
            headers['content-type'] = response.content_type
        if response.correlation_id:
            headers['X-Correlation-Id'] = response.correlation_id
        if response.data:
            headers['content-length'] = str(len(response.data))
        else:
            headers['content-length'] = '0'
        headers = [(name, value) for name, value in headers.items()]

        r = h11.Response(status_code=response.status.value, headers=headers,
                         reason=response.status.phrase)
        await self._send(r)
        data = response.data
        if data is not None:
            await self._send(h11.Data(data=data))
        await self._send(h11.EndOfMessage())

    async def _send(self, r):
        data = self.conn.send(r)
        self.writer.write(data)
        await self.writer.drain()

    async def get_request(self) -> Request:

        event = await self.next_event()
        if isinstance(event, h11.ConnectionClosed):
            raise ClosedError
        headers = {name.decode('ascii'): value.decode('ascii')
                   for name, value in event.headers}

        # split path and query string
        target = event.target.decode('ascii').split('?', maxsplit=1)
        path = target[0].lstrip(self.prefix)
        try:
            query = target[1]
        except IndexError:
            query = None
        method = event.method.decode('ascii')

        body = b''

        while True:
            event = await self.next_event()
            if type(event) is h11.EndOfMessage:
                break
            body += event.data
        correlation_id = headers.get('x-correlation-id')
        return Request(
            headers=headers,
            method=method,
            query_string=query,
            path=path,
            body=body,
            correlation_id=correlation_id
        )

    async def next_event(self):
        while True:
            event = self.conn.next_event()
            if event is h11.NEED_DATA:
                await self._read()
            else:
                return event
