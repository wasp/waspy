import traceback
from typing import List, Union, Iterable
import asyncio

from .webtypes import Request, Response, ResponseError
from .transports.transportabc import TransportABC
from .transports.httptransport import HTTPTransport
from .router import Router


class Application:
    def __init__(self,
                 transport: Union[TransportABC, Iterable[TransportABC]]=None,
                 *,
                 middlewares: List[callable]=None,
                 default_headers=None,
                 debug: bool=False,
                 router: Router=None):
        if transport is None:
            transport = HTTPTransport()
        if not isinstance(transport, tuple):
            transport = transport,
        if middlewares is None:
            middlewares = []
        if router is None:
            router = Router()
        if default_headers is None:
            default_headers = {'Server': 'wasp'}
        self.transport = transport
        self.middlewares = middlewares
        self.default_headers = default_headers
        self.debug = debug
        self.router = router
        self.on_start = []

    def run(self):
        loop = asyncio.get_event_loop()
        # todo: Call on-startup hook
        for t in self.transport:
            t.listen(loop=loop)

        for coro in self.on_start:
            loop.run_until_complete(coro(self))

        # todo: fork/add processes
        for t in self.transport:
            t.start(self, loop=loop)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print('Shutting down')

            # todo: Call on-shutdown hook
        for t in self.transport:
            t.shutdown(loop=loop)

        loop.close()

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
