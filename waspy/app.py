import asyncio
import logging
import signal
import sys
from functools import wraps
from typing import List, Union, Iterable
from http import HTTPStatus
from concurrent.futures import CancelledError

from ._cors import CORSHandler
from .client import Client
from .webtypes import Request, Response, ResponseError
from .router import Router
from .transports.transportabc import TransportABC
from .transports.rabbitmqtransport import NackMePleaseError
from .configuration import Config, ConfigError
from . import errorlogging


logging.basicConfig(format='%(asctime)s %(levelname)s [%(module)s.%(funcName)s] %(message)s')
logger = logging.getLogger('waspy')


async def response_wrapper_factory(app, handler):
    @wraps(handler)
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
                 config: Config=None,
                 loop=None):
        if transport is None:
            from waspy.transports.httptransport import HTTPTransport
            transport = HTTPTransport()
        if isinstance(transport, list):   
            transport = tuple(transport)
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
        self.on_stop = []
        self._client = None
        self.config = config
        self.raven = None
        self.logger = None
        self._cors_handler = None
        self.loop = loop

    @property
    def client(self) -> Client:
        if not self._client:
            self._client = Client(transport=self.transport[0].get_client())
        return self._client

    def start_shutdown(self, signum=None, frame=None):
        # loop = asyncio.get_event_loop()
        for t in self.transport:
            t.shutdown()

    def run(self):
        if not self.loop:
            self.loop = asyncio.get_event_loop()
        loop = self.loop

        if self.config['debug']:
            logger.setLevel('DEBUG')
            self.loop.set_debug(True)

        # init logger
        self._create_logger()

        # add cors support if needed
        self._cors_handler = CORSHandler.from_config(self.config)
        if self._cors_handler:
            self.router.add_generic_options_handler(self._cors_handler.options_handler)

        # wrap handlers in middleware
        loop.run_until_complete(self._wrap_handlers())
        for t in self.transport:
            t.listen(loop=loop, config=self.config)

        # Call on-startup hooks
        loop.run_until_complete(self.run_on_start_hooks())

        # todo: fork/add processes?
        tasks = []
        for t in self.transport:
            tasks.append(t.start(self.handle_request))

        # register signals, so that stopping the service works correctly
        loop.add_signal_handler(signal.SIGTERM, self.start_shutdown)
        loop.add_signal_handler(signal.SIGINT, self.start_shutdown)

        # Run all transports - they shouldn't return until shutdown
        loop.run_until_complete(asyncio.gather(*tasks))

        self.shutdown()

    async def run_on_start_hooks(self):
        """
        Run all hooks in on_start. Allows for coroutines and synchronous functions.
        """
        logger.debug("Running on start hooks")
        await self._run_hooks(self.on_start)

    async def run_on_stop_hooks(self):
        """
        Run all hooks in on_stop. Allows for coroutines and synchronous functions.
        """
        logger.debug("Running on stop hooks")
        await self._run_hooks(self.on_stop)


    async def handle_request(self, request: Request) -> Response:
        """
        coroutine: This method is called by Transport
        implementation to handle the actual request.
        It returns a webtype.Response object.
        """
        # Get handler
        try:
            try:
                handler = self.router.get_handler_for_request(request)
                request.app = self
                response = await handler(request)

            except ResponseError as r:
                response = r.response
                if r.log:
                    exc_info = sys.exc_info()
                    self.logger.log_exception(request, exc_info, level='warning')
            # invoke serialization (json) to make sure it works
            _ = response.data

        except CancelledError:
            # This error can happen if a client closes the connection
            # The response shouldnt really ever be used
            return None

        except NackMePleaseError:
            """ See message where this error is defined """
            raise

        except Exception:
            exc_info = sys.exc_info()
            self.logger.log_exception(request, exc_info)
            response = Response(status=500,
                                body={'message': 'Server Error'})
        if not response.correlation_id:
            response.correlation_id = request.correlation_id

        if self._cors_handler is not None:
            self._cors_handler.add_cors_headers(request, response)

        # add default headers
        response.headers = {**self.default_headers, **response.headers}

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
        except (ConfigError, ValueError):
            self.logger = errorlogging.ErrorLoggingBase()
        else:
            try:
                env = self.config['app_env']
            except (ConfigError):
                env = 'waspy'
            self.logger = errorlogging.SentryLogging(
                dsn=dsn,
                environment=env
            )

    async def _run_hooks(self, hooks):
        coros = []
        while len(hooks):
            task = hooks.pop()
            if asyncio.iscoroutinefunction(task):
                coros.append(task(self))
            else:
                task(self)
        await asyncio.gather(*coros)

    def shutdown(self):
        self.loop.run_until_complete(self.run_on_stop_hooks())
        self.loop.close()
