import asyncio
import socket
import weakref

import h11

from ..webtypes import Request, Response
from .transportabc import TransportABC


class ClosedError(Exception):
    """ Error for closed connections """


class HTTPTransport(TransportABC):
    def __init__(self, port=8080):
        self.port = port
        self._app = None
        self._server = None

    def listen(self, *, loop: asyncio.AbstractEventLoop):
        coro = asyncio.start_server(
            self.handle_incoming_request, '0.0.0.0', self.port, loop=loop)
        self._server = loop.run_until_complete(coro)

    def start(self, app, *, loop: asyncio.AbstractEventLoop):
        self._app = weakref.ref(app)()

    async def handle_incoming_request(self, reader, writer):
        self._set_tcp_nodelay(writer)
        protocol = HttpProtocol(reader=reader, writer=writer)

        try:
            while True:
                request = await protocol.get_request()
                response = await self._app.handle_request(request)
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


class HttpProtocol(asyncio.Protocol):
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
        r = h11.Response(status_code=response.status, headers=headers,
                         reason=response.reason)
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
        host = headers.pop('host', None)
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
            host=host,
            correlation_id=None
        )

    async def next_event(self):
        while True:
            event = self.conn.next_event()
            if event is h11.NEED_DATA:
                await self._read()
            else:
                return event
