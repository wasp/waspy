import asyncio
import logging
import urllib.parse
import uuid
import os

import aioamqp
import re
from aioamqp import channel, protocol

from .transportabc import TransportABC, ClientTransportABC, WorkerTransportABC
from ..webtypes import Request, Response, Methods, NotRoutableError


logger = logging.getLogger("waspy")


""" This is ugly, but you do what you gotta do

So... on that note: Lets do some monkey patching!!
We need to support mandatory bit, and handle returned messages, but
aioamqp doesnt support it yet. 
(follow https://github.com/Polyconseil/aioamqp/pull/158)

monkey patching _write_frame_awaiting_response fixes a waiter error. 
(follow PR here: https://github.com/Polyconseil/aioamqp/pull/159)

"""
import io
from aioamqp import frame as amqp_frame
from aioamqp import constants as amqp_constants


class ReturnEnvelope:
    __slots__ = ('reply_code', 'reply_text',
                 'exchange_name', 'routing_key')

    def __init__(self, reply_code, reply_text, exchange_name, routing_key):
        self.reply_code = reply_code
        self.reply_text = reply_text
        self.exchange_name = exchange_name
        self.routing_key = routing_key


async def basic_return(self, frame):
    response = amqp_frame.AmqpDecoder(frame.payload)
    reply_code = response.read_short()
    reply_text = response.read_shortstr()
    exchange_name = response.read_shortstr()
    routing_key = response.read_shortstr()
    content_header_frame = await self.protocol.get_frame()

    buffer = io.BytesIO()
    while buffer.tell() < content_header_frame.body_size:
        content_body_frame = await self.protocol.get_frame()
        buffer.write(content_body_frame.payload)

    body = buffer.getvalue()
    envelope = ReturnEnvelope(reply_code, reply_text,
                              exchange_name, routing_key)
    properties = content_header_frame.properties
    callback = self.return_callback
    if self.return_callback is None:
        # they have set mandatory bit, but havent added a callback
        logger.warning(
            'You have received a returned message, but dont have a callback registered for returns.'
            ' Please set channel.return_callback')
    else:
        await callback(self, body, envelope, properties)


async def dispatch_frame(self, frame):
    methods = {
        (amqp_constants.CLASS_CHANNEL, amqp_constants.CHANNEL_OPEN_OK): self.open_ok,
        (amqp_constants.CLASS_CHANNEL, amqp_constants.CHANNEL_FLOW_OK): self.flow_ok,
        (amqp_constants.CLASS_CHANNEL, amqp_constants.CHANNEL_CLOSE_OK): self.close_ok,
        (amqp_constants.CLASS_CHANNEL, amqp_constants.CHANNEL_CLOSE): self.server_channel_close,

        (amqp_constants.CLASS_EXCHANGE, amqp_constants.EXCHANGE_DECLARE_OK): self.exchange_declare_ok,
        (amqp_constants.CLASS_EXCHANGE, amqp_constants.EXCHANGE_BIND_OK): self.exchange_bind_ok,
        (amqp_constants.CLASS_EXCHANGE, amqp_constants.EXCHANGE_UNBIND_OK): self.exchange_unbind_ok,
        (amqp_constants.CLASS_EXCHANGE, amqp_constants.EXCHANGE_DELETE_OK): self.exchange_delete_ok,

        (amqp_constants.CLASS_QUEUE, amqp_constants.QUEUE_DECLARE_OK): self.queue_declare_ok,
        (amqp_constants.CLASS_QUEUE, amqp_constants.QUEUE_DELETE_OK): self.queue_delete_ok,
        (amqp_constants.CLASS_QUEUE, amqp_constants.QUEUE_BIND_OK): self.queue_bind_ok,
        (amqp_constants.CLASS_QUEUE, amqp_constants.QUEUE_UNBIND_OK): self.queue_unbind_ok,
        (amqp_constants.CLASS_QUEUE, amqp_constants.QUEUE_PURGE_OK): self.queue_purge_ok,

        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_QOS_OK): self.basic_qos_ok,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_CONSUME_OK): self.basic_consume_ok,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_CANCEL_OK): self.basic_cancel_ok,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_GET_OK): self.basic_get_ok,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_GET_EMPTY): self.basic_get_empty,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_DELIVER): self.basic_deliver,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_CANCEL): self.server_basic_cancel,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_ACK): self.basic_server_ack,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_NACK): self.basic_server_nack,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_RECOVER_OK): self.basic_recover_ok,
        (amqp_constants.CLASS_BASIC, amqp_constants.BASIC_RETURN): self.basic_return,

        (amqp_constants.CLASS_CONFIRM, amqp_constants.CONFIRM_SELECT_OK): self.confirm_select_ok,
    }

    if (frame.class_id, frame.method_id) not in methods:
        raise NotImplementedError("Frame (%s, %s) is not implemented" % (frame.class_id, frame.method_id))
    await methods[(frame.class_id, frame.method_id)](frame)


async def _write_frame_awaiting_response(self, waiter_id, frame, request,
                                         no_wait, check_open=True, drain=True):
    '''Write a frame and set a waiter for
    the response (unless no_wait is set)'''
    if no_wait:
        await self._write_frame(frame, request, check_open=check_open,
                                     drain=drain)
        return None

    f = self._set_waiter(waiter_id)
    try:
        await self._write_frame(frame, request, check_open=check_open,
                                     drain=drain)
    except Exception:
        self._get_waiter(waiter_id)
        f.cancel()
        raise
    result = await f
    try:
        self._get_waiter(waiter_id)
    except aioamqp.SynchronizationError:
        # no waiter to get
        pass
    return result

channel.Channel._write_frame_awaiting_response = _write_frame_awaiting_response
channel.Channel.dispatch_frame = dispatch_frame
channel.Channel.basic_return = basic_return

""" End of monkey patching"""


class NackMePleaseError(Exception):
    """ This is a dirty dirty dirty dirty hack that is in place until
        I have time to add a real worker tier type connector support in waspy
        TODO: Please get rid of this as soon as your able to
    """


from aioamqp.channel import Channel


def parse_rabbit_message(body, envelope, properties):
    return Response()


class RabbitChannelMixIn:
    def __init__(self):
        self._channel_ready = asyncio.Event()

    async def _bootstrap_channel(self, channel):
        raise NotImplementedError

    async def _handle_rabbit_error(self, exception):
        try:
            raise exception
        except (aioamqp.ChannelClosed, aioamqp.AmqpClosedConnection):
            '''logger.exception("Rabbitmq channel closed")'''

    async def disconnect(self):
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
            channel = None
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
                                         payload=body,
                                         mandatory=mandatory)

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
        future = self._response_futures[properties.message_id]

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
        future = self._response_futures.get(properties.message_id, None)
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
        self.heartbeat = heartbeat
        self._config = {}

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

            payload = response.data or b'None'

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


class RabbitMQWorkerTransport(RabbitMQTransport, WorkerTransportABC):
    def __init__(self, *, url, port=5672, queue='', virtualhost='/',
                 username='guest', password='guest',
                 ssl=False, verify_ssl=True, create_queue=True, heartbeat=20):
        super().__init__(url=url, port=port, queue=queue,
                         virtualhost=virtualhost, username=username,
                         password=password, ssl=ssl, verify_ssl=verify_ssl,
                         create_queue=create_queue, use_acks=True,
                         heartbeat=heartbeat)
        self._worker = None

    def start(self, worker):
        print(f"-- Listening for rabbitmq messages on queue {self.queue} --")
        self._worker = worker
