import asyncio
import logging
import uuid

import aioamqp
import re
from aioamqp.channel import Channel

from .transportabc import TransportABC, ClientTransportABC
from ..webtypes import Request, Response, Methods


logger = logging.getLogger("waspy")


class RabbitChannelMixIn:
    async def _bootstrap_channel(self, channel):
        raise NotImplementedError

    async def _handle_rabbit_error(self, exception):
        print(exception)
        try:
            raise exception
        except (aioamqp.ChannelClosed, aioamqp.AmqpClosedConnection):
            if not self._closing:
                self._starting_future = asyncio.ensure_future(self.connect())

    async def connect(self, loop=None):
        if self.channel and self.channel.is_open:
            return
        channel = None
        if self._protocol and not self._protocol.connection_closed.is_set():
            try:  # getting a new channel from existing protocol
                channel = await self._protocol.channel()
            except aioamqp.AioamqpException:
                # ok, that didnt work
                channel = None
        if not channel:
            self._transport, self._protocol = await aioamqp.connect(
                host=self.host,
                port=self.port,
                virtualhost=self.virtualhost,
                login=self.username,
                password=self.password,
                ssl=self.ssl,
                verify_ssl=self.verify_ssl,
                heartbeat=20,
                on_error=self._handle_rabbit_error,
                loop=loop
            )
            channel = await self._protocol.channel()
        await self._bootstrap_channel(channel)


class RabbitMQClientTransport(ClientTransportABC, RabbitChannelMixIn):
    def __init__(self, *, url=None, port=5672, virtualhost='/',
                 username='guest', password='guest',
                 ssl=False, verify_ssl=True):

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

        if not url:
            raise TypeError("RabbitMqClientTransport() missing 1 required keyword-only argument: 'url'")

        self._starting_future: asyncio.Future = asyncio.ensure_future(self.connect())

    async def make_request(self, service: str, method: str, path: str,
                           body: bytes = None, query: str = None,
                           headers: dict = None, correlation_id: str = None,
                           content_type: str = None,
                           exchange: str = 'amq.topic',
                           timeout: int = 30,
                           **kwargs):

        if not self._starting_future.done():
            await self._starting_future
        if self._starting_future.exception():
            raise self._starting_future.exception()
        path = f'{method.lower()}.' + path.replace('/', '.').lstrip('.')
        if headers is None:
            headers = {}
        if query:
            headers['x-wasp-query-string'] = query

        if not body:
            body = b'None'
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

        await self.channel.basic_publish(exchange_name=exchange,
                                         routing_key=path,
                                         properties=properties,
                                         payload=body)

        if method != 'PUBLISH':
            future = asyncio.Future()
            self._response_futures[message_id] = future
            return await future

    async def _bootstrap_channel(self, channel: Channel):
        if self.channel and self.channel.open():
            await self.channel.close()
        self.channel = channel
        await self.channel.queue_declare(queue_name=self.response_queue_name,
                                         durable=False,
                                         exclusive=False,
                                         auto_delete=True)
        self._consumer_tag = (await self.channel.basic_consume(
            self.handle_responses,
            queue_name=self.response_queue_name,
            no_ack=True)).get('consumer_tag')

    async def handle_responses(self, channel, body, envelope, properties):
        future = self._response_futures[properties.message_id]

        headers = properties.headers
        status = headers.pop('Status')

        response = Response(headers=headers,
                            correlation_id=properties.correlation_id,
                            body=body,
                            status=status,
                            content_type=properties.content_type)

        future.set_result(response)

    async def close(self):
        self._closing = True
        await self._protocol.close()
        self._transport.close()


class RabbitMQTransport(TransportABC, RabbitChannelMixIn):
    def __init__(self, *, url, port=5672, queue='', virtualhost='/',
                 username='guest', password='guest',
                 ssl=False, verify_ssl=True, create_queue=True,
                 use_acks=False):
        self.host = url
        self.port = port
        self.virtualhost = virtualhost
        self.queue = queue
        self.username = username
        self.password = password
        self.ssl = ssl
        self.verify_ssl = verify_ssl
        self.create_queue = create_queue
        self._use_acks=use_acks
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
        self._starting_future = None

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
        # ToDo: Need to reconnect because of potential forking affects
        # await self.close()
        # await self.connect()
        self._starting_future = asyncio.ensure_future(
            self._bootstrap_channel(self.channel))
        if not self._starting_future.done():
            await self._starting_future

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
        self._starting_future = loop.create_task(self.connect(loop=loop))

        async def setup():
            if not self._starting_future.done():
                await self._starting_future
            if self._starting_future.exception():
                raise self._starting_future.exception()
            if self.create_queue:
                await self.channel.queue_declare(queue_name=self.queue)

        loop.run_until_complete(setup())

    async def close(self):
        self._closing = True
        await self._protocol.close()
        if self._client:
            await self._client.close()
        self._transport.close()

    async def handle_request(self, channel: Channel, body, envelope,
                             properties, futurize=True):
        """
        the 'f' param is simply because aioamqp doesnt send another job until
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
        headers['content-type'] = properties.content_type
        headers['content-encoding'] = properties.content_encoding
        correlation_id = properties.correlation_id
        message_id = properties.message_id
        reply_to = properties.reply_to
        route = envelope.routing_key
        method, path = route.split('.', 1)
        try:
            method = Methods(method.upper())
        except ValueError:
            path = f'{method}.{path}'
            method = 'POST'

        request = Request(
            headers=headers,
            path=path,
            correlation_id=correlation_id,
            method=method,
            query_string=query,
            body=body,
        )

        response = await self._handler(request)
        if response is None:
            # task got cancelled. Dont send a response.
            return
        if reply_to:
            response.headers['Status'] = str(response.status.value)

            payload = response.data or b'None'

            properties = {
                'correlation_id': response.correlation_id,
                'headers': response.headers,
                'content_type': response.content_type,
                'message_id': message_id,
                'expiration': '30000',
            }
            if not self._starting_future.done:
                await self._starting_future
            if self._starting_future.exception():
                raise self._starting_future.exception()
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
            # we havent started yet
            return

        await self.channel.basic_qos(prefetch_count=1)
        resp = await self.channel.basic_consume(
            self.handle_request,
            queue_name=self.queue,
            no_ack=not self._use_acks
        )
        self._consumer_tag = resp.get('consumer_tag')


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
    route = route.replace('/', '.').lstrip('.')
    topic = f'{method.value.lower()}.{route}'
    return re.sub(r"\.\{[^\}]*\}[:\w\d_-]*", ".*", topic)
