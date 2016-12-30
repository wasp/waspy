import asyncio
import socket

import h11

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

    def __init__(self, port=8080):
        self.port = port
        self._handler = None
        self._server = None

    def listen(self, *, loop: asyncio.AbstractEventLoop):
        coro = asyncio.start_server(
            self.handle_incoming_request, '0.0.0.0', self.port, loop=loop)
        self._server = loop.run_until_complete(coro)
        print('-- Listening for HTTP on port {} --'.format(self.port))

    def start(self, request_handler, *, loop: asyncio.AbstractEventLoop):
        self._handler = request_handler

    async def handle_incoming_request(self, reader, writer):
        self._set_tcp_nodelay(writer)
        protocol = _HTTPServerProtocol(reader=reader, writer=writer)

        try:
            while True:
                request = await protocol.get_request()
                response = await self._handler(request)
                await protocol.send_response(response)
                if protocol.conn.our_state is h11.MUST_CLOSE:
                    break
                protocol.conn.start_next_cycle()
        except (ClosedError, ConnectionResetError):
            pass
        writer.close()

    def shutdown(self, *, loop):
        self._server.close()
        loop.run_until_complete(self._server.wait_closed())

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

    def __init__(self, reader=None, writer=None):
        self.conn = h11.Connection(h11.SERVER)
        self.reader = reader
        self.writer = writer

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
        headers = [(name, value) for name, value in response.headers.items()]
        r = h11.Response(status_code=response.status.value, headers=headers,
                         reason=response.status.phrase)
        await self._send(r)
        await self._send(h11.Data(data=response.data))
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
        path = target[0]
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

        return Request(
            headers=headers,
            method=method,
            query_string=query,
            path=path,
            body=body,
            correlation_id=None
        )

    async def next_event(self):
        while True:
            event = self.conn.next_event()
            if event is h11.NEED_DATA:
                await self._read()
            else:
                return event
