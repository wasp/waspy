from . import rabbit_patches

import asyncio
import logging
import urllib.parse
import uuid
import os

import aioamqp
import re
from aioamqp import protocol
from aioamqp.channel import Channel


from .transportabc import TransportABC, ClientTransportABC, WorkerTransportABC
from ..webtypes import Request, Response, Methods
from ..exceptions import NotRoutableError
from waspy.listeners.transport_listener_abc import TransportListenerABC


logger = logging.getLogger("waspy")


class NackMePleaseError(Exception):
    """ This is a dirty dirty dirty dirty hack that is in place until
        I have time to add a real worker tier type connector support in waspy
        TODO: Please get rid of this as soon as your able to
    """


def parse_rabbit_message(body, envelope, properties):
    return Response()


class RabbitChannelMixIn:
    def __init__(self):
        self.channel = None
        self._channel_ready = asyncio.Event()

        self.channels = {}

    async def _bootstrap_channel(self, channel):
        raise NotImplementedError

    async def _handle_rabbit_error(self, exception):
        if type(exception) == aioamqp.ChannelClosed:
            if self._protocol and self._protocol.state not in (protocol.CLOSING, protocol.CLOSED):
                logger.warning("RabbitMQ channel closed... Creating new channel")
                self._channel_ready.clear()
                self.channel = None
                channel = await self._protocol.channel()
                await self._bootstrap_channel(channel)
                self._channel_ready.set()
        elif type(exception) == aioamqp.AmqpClosedConnection:
            logger.error("RabbitMQ connection closed")
        else:
            logger.error(f"Unknown exception occurred: {exception}")
            raise exception

    async def create_channel(self) -> aioamqp.channel.Channel:
        channel = await self._protocol.channel()
        self.channels[channel.channel_id] = channel
        return channel
    
    async def close_channel(self, channel: aioamqp.channel.Channel) -> None:
        del self.channels[channel.channel_id]
        await channel.close()

    async def disconnect(self):
        for channel in self.channels.values():
            if channel.is_open:
                await channel.close()
        
        self.channels = {}
        if self._protocol and self._protocol.state != protocol.CLOSED:
            if self._protocol.state == protocol.CLOSING:
                await self._protocol.wait_closed()
            else:
                await self._protocol.close()
        if self._transport:
            self._transport.close()

    async def connect(self, loop=None):
        async def do_connect():
            if self.channel and self.channel.is_open:
                return
            logger.warning('Establishing new connection')
            if self._protocol:
                await self.disconnect()

            if os.getenv('DEBUG', 'false') == 'true':
                # todo: should make this use config and logging, and not env vars
                print(dict(host=self.host,
                           port=self.port,
                           virtualhost=self.virtualhost,
                           login=self.username,
                           password='*******',
                           ssl=self.ssl,
                           verify_ssl=self.verify_ssl,
                           heartbeat=self.heartbeat,
                           on_error=self._handle_rabbit_error,
                           loop=loop))
            self._transport, self._protocol = await aioamqp.connect(
                host=self.host,
                port=self.port,
                virtualhost=self.virtualhost,
                login=self.username,
                password=self.password,
                ssl=self.ssl,
                verify_ssl=self.verify_ssl,
                heartbeat=self.heartbeat,
                on_error=self._handle_rabbit_error,
                loop=loop
            )
            channel = await self._protocol.channel()

            await self._bootstrap_channel(channel)
            self._channel_ready.set()

        async def reconnect():
            try:
                while not self._closing:
                    await do_connect()
                    if hasattr(self, 'listeners'):
                        for listener in self.listeners:
                            channel = await self.create_channel()
                            await listener.set_channel(channel)
                            await listener.start()
                    await self._protocol.wait_closed()
                    self._channel_ready.clear()
                    self.channel = None

                    await self.disconnect()
            finally:
                await self.disconnect()

        asyncio.ensure_future(reconnect())


class RabbitMQClientTransport(ClientTransportABC, RabbitChannelMixIn):
    _CLOSING_SENTINAL = object()

    def __init__(self, *, url=None, port=5672, virtualhost='/',
                 username='guest', password='guest',
                 ssl=False, verify_ssl=True, heartbeat=20):

        super().__init__()
        self._transport = None
        self._protocol = None
        self._response_futures = {}
        self.host = url
        self.port = port
        self.virtualhost = virtualhost
        self.username = username
        self.password = password
        self.ssl = ssl
        self.verify_ssl = verify_ssl

        self.response_queue_name = str(uuid.uuid1()).encode()
        self._consumer_tag = None
        self._closing = False
        self.channel = None
        self.heartbeat = heartbeat
        self._connected = False

        if not url:
            raise TypeError("RabbitMqClientTransport() missing 1 required keyword-only argument: 'url'")

    async def make_request(self,
                           service: str,
                           method: str,
                           path: str,
                           body: bytes = None,
                           query: str = None,
                           headers: dict = None,
                           correlation_id: str = None,
                           content_type: str = None,
                           exchange: str = 'amq.topic',
                           timeout: int = 30,
                           mandatory: bool = False,
                           **kwargs):

        if not self._connected:
            self._connected = True
            asyncio.ensure_future(self.connect())
        await self._channel_ready.wait()

        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        # need to use `?` to represent `.` in rabbit
        # since its not valid in a path, it should work correctly everywhere
        path = path.replace('.', '?')

        # now turn slashes into dots for rabbit style paths
        path = path.replace('/', '.').lstrip('.')

        if method != 'PUBLISH':
            path = f'{method.lower()}.' + path

        if headers is None:
            headers = {}
        if query:
            headers['x-wasp-query-string'] = query

        if not body:
            body = b'null'
        message_id = str(uuid.uuid4())
        properties = {
            'headers': headers,
            'correlation_id': correlation_id,
            'message_id': message_id,
            'type': method,
            'app_id': 'test',
        }
        if method != 'PUBLISH':
            properties['reply_to'] = self.response_queue_name
            properties['expiration']: str(timeout * 1000)

        if content_type:
            properties['content_type'] = content_type

        try:
            await self.channel.basic_publish(exchange_name=exchange,
                                             routing_key=path,
                                             properties=properties,
                                             payload=body,
                                             mandatory=mandatory)
        except aioamqp.AmqpClosedConnection as e:
            """ Usually this means that rabbitmq closed the connection, because something was bad,
                such as the exchange name, or something """
            self._handle_rabbit_error(e)
            raise

        if method != 'PUBLISH':
            future = asyncio.Future()
            self._response_futures[message_id] = future
            return await future

    async def _bootstrap_channel(self, channel: Channel):
        if self.channel == channel:
            logger.warning("somehow the channels are the same on a bootstrap")
        if self.channel and self.channel.is_open:
            await self.channel.close()
        self.channel = channel
        await self.channel.queue_declare(queue_name=self.response_queue_name,
                                         durable=False,
                                         exclusive=False,
                                         auto_delete=True)
        self.channel.return_callback = self.handle_return
        try:
            self._consumer_tag = (await self.channel.basic_consume(
                self.handle_responses,
                queue_name=self.response_queue_name,
                no_ack=True)).get('consumer_tag')
        except aioamqp.SynchronizationError as e:
            logger.exception('Channel already consuming')
            raise

    async def handle_responses(self, channel, body, envelope, properties):
        future = self._response_futures.pop(properties.message_id)

        headers = properties.headers
        status = headers.pop('Status')

        response = Response(headers=headers,
                            correlation_id=properties.correlation_id,
                            body=body,
                            status=int(status),
                            content_type=properties.content_type)
        if not future.done():
            future.set_result(response)

    async def handle_return(self, channel, body, envelope, properties):
        future = self._response_futures.pop(properties.message_id, None)
        if not future:
            logger.warning('Got a returned message with nowhere to send it')
            return
        if envelope.reply_code == 312:
            # no route
            future.set_exception(NotRoutableError())
        else:
            logger.error(f'Got a return with an unknown reply code: '
                         f'{envelope.reply_code}')

    async def close(self):
        self._closing = True
        await self.disconnect()


class RabbitMQTransport(TransportABC, RabbitChannelMixIn):
    def __init__(self, *, url, port=5672, queue='', virtualhost='/',
                 username='guest', password='guest',
                 ssl=False, verify_ssl=True, create_queue=True,
                 use_acks=False, heartbeat=20):
        super().__init__()
        self.host = url
        self.port = port
        self.virtualhost = virtualhost
        self.queue = queue
        self.username = username
        self.password = password
        self.ssl = ssl
        self.verify_ssl = verify_ssl
        self.create_queue = create_queue
        self._use_acks = use_acks
        self._transport = None
        self._protocol = None
        self.channel = None
        self._app = None
        self._loop = None
        self._consumer_tag = None
        self._counter = 0
        self._handler = None
        self._done_future = asyncio.Future()
        self._closing = False
        self._client = None
        self.heartbeat = heartbeat
        self._config = {}

        self.listeners = []

    def get_client(self):
        if not self._client:
            # TODO: not ideal, the client/server should ideally share a channel
            #   or at least a connection
            self._client = RabbitMQClientTransport(
                url=self.host,
                port=self.port,
                virtualhost=self.virtualhost,
                username=self.username,
                password=self.password,
                ssl=self.ssl,
                verify_ssl=self.verify_ssl)

        return self._client

    async def declare_exchange(self):
        pass

    async def declare_queue(self):
        pass

    async def bind_to_exchange(self, *, exchange, routing_key):
        await self.channel.queue_bind(exchange_name=exchange,
                                      queue_name=self.queue,
                                      routing_key=routing_key)

    async def register_router(self, router, exchange='amq.topic'):
        if not self.channel:
            # Something weird is going on here?
            return

        for topic in (parse_url_to_topic(*url) for url in router.urls):
            await self.bind_to_exchange(exchange=exchange, routing_key=topic)

    async def start(self, handler):
        print(f"-- Listening for rabbitmq messages on queue {self.queue} --")
        self._handler = handler

        await self._channel_ready.wait()

        # channel hasn't actually been bootstraped yet
        await self._bootstrap_channel(self.channel)

        try:
            await self._done_future
        except asyncio.CancelledError:
            pass

        # shutting down
        logger.warning("Shutting down rabbitmq transport")
        await self.channel.basic_cancel(self._consumer_tag)
        await self.close()
        while self._counter > 0:
            await asyncio.sleep(1)

    def listen(self, *, loop, config):
        loop.create_task(self.connect(loop=loop))
        self._config = config

        async def setup():
            await self._channel_ready.wait()
            if self.create_queue:
                await self.channel.queue_declare(queue_name=self.queue)

        loop.run_until_complete(setup())

    async def close(self):
        self._closing = True
        if self._client:
            await self._client.close()
        await self.disconnect()

    async def handle_request(self, channel: Channel, body, envelope,
                             properties, futurize=True):
        """
        the 'futurize' param is simply because aioamqp doesnt send another job until
         this method returns (completes), so we ensure the future of
         ourselves and return immediately so we can handle many requests
         at a time.
        """
        if futurize:
            asyncio.ensure_future(
                self.handle_request(channel, body, envelope, properties,
                                    futurize=False))
            return

        self._counter += 1
        headers = properties.headers or {}
        query = headers.pop('x-wasp-query-string', '').lstrip('?')
        correlation_id = properties.correlation_id
        message_id = properties.message_id
        reply_to = properties.reply_to
        route = envelope.routing_key

        method, path = route.split('.', 1)
        try:
            method = Methods(method.upper())
        except ValueError:
            path = route
            method = 'POST'
        path = path.replace('.', '/')
        # need to use `?` to represent `.` in rabbit
        # since its not valid in a path, it should work correctly everywhere
        path = path.replace('?', '.')
        path = urllib.parse.unquote(path)

        request = Request(
            headers=headers,
            path=path,
            correlation_id=correlation_id,
            method=method,
            query_string=query,
            body=body,
        )
        if properties.content_type:
            headers['content-type'] = properties.content_type
            request.content_type = properties.content_type
        if properties.content_encoding:
            headers['content-encoding'] = properties.content_encoding

        logger.debug('received incoming request via rabbitmq: %s', request)
        response = await self._handler(request)
        if response is None:
            # task got cancelled. Dont send a response.
            return
        if reply_to:
            response.headers['Status'] = str(response.status.value)

            payload = response.raw_body or b'null'

            properties = {
                'correlation_id': response.correlation_id,
                'headers': response.headers,
                'content_type': response.content_type,
                'message_id': message_id,
                'expiration': '30000',
            }
            await self._channel_ready.wait()
            await channel.basic_publish(exchange_name='',
                                        payload=payload,
                                        routing_key=reply_to,
                                        properties=properties)

        if self._use_acks:
            await self.channel.basic_client_ack(delivery_tag=envelope.delivery_tag)
        self._counter -= 1

    def shutdown(self):
        self._done_future.cancel()

    async def _bootstrap_channel(self, channel):
        self.channel = channel

        if self._handler is None:
            return

        await self.channel.basic_qos(prefetch_count=1)
        resp = await self.channel.basic_consume(
            self.handle_request,
            queue_name=self.queue,
            no_ack=not self._use_acks
        )
        self._consumer_tag = resp.get('consumer_tag')

    def add_listener(self, listener: TransportListenerABC):
        self.listeners.append(listener)
        listener.set_transport(self)

def parse_url_to_topic(method, route):
    """
    Transforms a URL to a topic.

    `GET /bar/{id}` -> `get.bar.*`
    `POST /bar/{id}` -> `post.bar.*`
    `GET /foo/bar/{id}/baz` -? `get.foo.bar.*.baz`

    Possible gotchas

    `GET /foo/{id}` -> `get.foo.*`
    `GET /foo/{id}:action` -> `get.foo.*`

    However, once it hits the service the router will be able to distinguish the two requests.
    """
    route = route.replace('.', '?')
    route = route.replace('/', '.').strip('.')
    topic = f'{method.value.lower()}.{route}'
    # need to replace `{id}` and `{id}:some_method` with just `*`
    return re.sub(r"\.\{[^\}]*\}[:\w\d_-]*", ".*", topic)
