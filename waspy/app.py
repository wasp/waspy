import sys
from typing import List, Union, Iterable
import asyncio
from http import HTTPStatus
from concurrent.futures import CancelledError

from .client import Client
from .webtypes import Request, Response, ResponseError
from .router import Router
from .transports.transportabc import TransportABC
from .configuration import Config, ConfigError
from . import errorlogging


async def response_wrapper_factory(app, handler):
    async def wrap_response_middleware(request):
        response = await handler(request)
        if not isinstance(response, Response):
            if isinstance(response, tuple):
                body = response[0]
                status = response[1]
                response = Response(status=status, body=body)
            elif isinstance(response, dict) or isinstance(response, str):
                response = Response(body=response)
            elif response is None:
                response = Response(status=HTTPStatus.NO_CONTENT)
            else:
                raise ValueError('Request handler returned an invalid type.'
                                 ' Return types should be one of '
                                 '[Response, dict, str, None, (dict, int)]')
        return response
    return wrap_response_middleware


class Application:
    def __init__(self,
                 transport: Union[TransportABC,
                                  Iterable[TransportABC]]=None,
                 *,
                 middlewares: List[callable]=None,
                 default_headers: dict=None,
                 debug: bool=False,
                 router: Router=None,
                 config: Config=None):
        if transport is None:
            from waspy.transports.httptransport import HTTPTransport
            transport = HTTPTransport()
        if not isinstance(transport, tuple):
            transport = (transport,)
        if middlewares is None:
            middlewares = ()
        middlewares = tuple([m for m in middlewares])
        middlewares += (response_wrapper_factory,)
        if router is None:
            router = Router()
        if default_headers is None:
            default_headers = {'Server': 'waspy'}
        if not config:
            config = Config()
        self.transport = transport
        self.middlewares = middlewares
        self.default_headers = default_headers
        self.debug = debug
        self.router = router
        self.on_start = []
        self._client = None
        self.config = config
        self.raven = None
        self.logger = None

    @property
    def client(self) -> Client:
        if not self._client:
            self._client = Client(transport=self.transport[0].get_client())
        return self._client

    def run(self):
        loop = asyncio.get_event_loop()
        # init logger
        self._create_logger()

        # wrap handlers in middleware
        loop.run_until_complete(self._wrap_handlers())
        for t in self.transport:
            t.listen(loop=loop)

        # Call on-startup hooks
        for coro in self.on_start:
            loop.run_until_complete(coro(self))

        # todo: fork/add processes?
        for t in self.transport:
            t.start(self.handle_request, loop=loop)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print('Shutting down')
        for t in self.transport:
            t.shutdown(loop=loop)

        # todo: Call on-shutdown hooks

        loop.close()

    async def handle_request(self, request: Request) -> Response:
        """
        coroutine: This method is called by Transport
        implementation to handle the actual request.
        It returns a webtype.Response object.
        """
        # Get handler
        try:
            handler = self.router.get_handler_for_request(request)
            request.app = self
            response = await handler(request)

        except ResponseError as r:
            response = r.response
            if r.log:
                exc_info = sys.exc_info()
                self.logger.log_exception(request, exc_info, level='warning')
        except CancelledError:
            # This error can happen if a client closes the connection
            # The response shouldnt really ever be used
            return None
        except Exception:
            exc_info = sys.exc_info()
            self.logger.log_exception(request, exc_info)
            response = Response(status=500)
        if not response.correlation_id:
            response.correlation_id = request.correlation_id
        # add default headers
        extra_headers = {}
        if response.data is not None:
            extra_headers['content-length'] = str(len(response.data))
        else:
            extra_headers['content-length'] = '0'

        response.headers = {**self.default_headers, **extra_headers,
                            **response.headers}

        return response

    async def _wrap_handlers(self):
        handler_gen = self.router._get_and_wrap_routes()

        try:
            handler = next(handler_gen)
            while True:
                wrapped = handler
                for middleware in self.middlewares[::-1]:
                    wrapped = await middleware(self, wrapped)
                handler = handler_gen.send(wrapped)
        except StopIteration:
            pass

    def _create_logger(self):
        try:
            dsn = self.config['sentry']['dsn']
        except ConfigError:
            self.logger = errorlogging.ErrorLoggingBase()
        else:
            try:
                env = self.config['app_env']
            except ConfigError:
                env = 'waspy'
            self.logger = errorlogging.SentryLogging(
                dsn=dsn,
                environment=env
            )

