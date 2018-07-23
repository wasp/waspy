import asyncio
import json

from .. import webtypes
from .transportabc import TransportABC, ClientTransportABC


class TestClientTransport(ClientTransportABC):
    async def make_request(self, service: str, method: str, path: str,
                     body: bytes = None, query: str = None,
                     headers: dict = None, correlation_id: str = None,
                     content_type: str = None, **kwargs) -> webtypes.Response:
        pass


class TestTransport(TransportABC):
    def __init__(self, *args, **kwargs):
        self.app = None
        self.loop = None
        self.handler = None

    def listen(self, *, loop, config):
        self.loop = loop

    def run_app(self, app):
        self.app = app
        app.transport = (self,)
        app.shutdown = lambda: ''
        app.run()
        # now patch app to have send_request methods as well
        def send_request_for_app(request):
            return self.send_request(request)
        async def send_async_request_for_app(request):
            return await self.send_async_request(request)

        app.send_request = send_request_for_app
        app.send_async_request = send_async_request_for_app

    def send_request(self, request):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.send_async_request(request))

    async def send_async_request(self, request):
        if request.body and isinstance(request.body, dict):
            request.body = json.dumps(request.body)

        if isinstance(request.body, str):
            request.body = request.body.encode()

        response = await self.handler(request)
        response.body = response.body
        return response

    async def start(self, request_handler: callable):
        self.handler = request_handler

    def shutdown(self):
        pass

    def get_client(self):
        return TestClientTransport()
