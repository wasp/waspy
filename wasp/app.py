import traceback
from typing import List
import asyncio

from .webtypes import Request, Response, ResponseError
from .transports.transportabc import TransportABC
from .transports.httptransport import HTTPTransport
from .router import Router


class Application:
    def __init__(self,
                 transport: TransportABC=None,
                 *,
                 middlewares: List[callable]=None,
                 default_headers=None,
                 debug: bool=False,
                 router: Router=None):
        if transport is None:
            transport = HTTPTransport()
        if middlewares is None:
            middlewares = []
        if router is None:
            router = Router()
        if default_headers is None:
            default_headers = {}
        self.transport = transport
        self.middlewares = middlewares
        self.default_headers = default_headers
        self.debug = debug
        self.router = router

    def run(self):
        loop = asyncio.get_event_loop()
        # todo: Call on-startup hook
        self.transport.listen(loop=loop)

        # todo: fork/add processes
        self.transport.run(self, loop=loop)
        # todo: Call on-shutdown hook

    async def handle_request(self, request: Request) -> Response:
        """
        coroutine: This method is called by Transport
        implementation to handle the actual request.
        It returns a webtype.Response object.
        """
        # ToDo: Send through middlewares
        # response = Response(headers={'hello': 'world'}, body={'foo': 'bar'})
        # Get handler
        try:
            handler = self.router.get_handler_for_request(request)
            response = await handler(request)
            if not isinstance(response, Response):
                if isinstance(response, tuple):
                    body = response[0]
                    status = response[1]
                    response = Response(status=status, body=body)
                elif isinstance(response, dict):
                    response = Response(body=response)

        except ResponseError as r:
            response = r.response
        except Exception as e:
            traceback.print_exc()
            response = Response(status=500)
        # add default headers
        response.headers = {**self.default_headers, **response.headers}

        return response
