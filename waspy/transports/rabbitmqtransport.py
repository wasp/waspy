import weakref

import aioamqp
from aioamqp.channel import Channel
import asyncio

from .transportabc import TransportABC, ClientTransportABC
from ..webtypes import Request, Response


class RabbitMQClientTransport(ClientTransportABC):
    def __init__(self):
        raise NotImplementedError

    def make_request(self, service: str, method: str, path: str,
                     body: bytes = None, query: str = None,
                     headers: dict = None, correlation_id: str = None,
                     content_type: str = None, **kwargs):
        raise NotImplementedError


class RabbitMQTransport(TransportABC):
    def __init__(self, *, url, port=5672, queue='', virtualhost='/',
                 username='guest', password='guest',
                 ssl=False, verify_ssl=True):
        self.host = url
        self.port = port
        self.virtualhost = virtualhost
        self.queue = queue
        self.username = username
        self.password = password
        self.ssl = ssl
        self.verify_ssl = verify_ssl
        self._transport = None
        self._protocol = None
        self.channel = None
        self._app = None
        self._loop = None
        self._consumer_tag = None
        self._counter = 0

    def get_client(self):
        pass

    async def declare_exchange(self):
        pass

    async def declare_queue(self):
        pass

    async def bind_to_exchange(self, *, exchange, routing_key):
        await self.channel.queue_bind(exchange_name=exchange,
                                      queue_name=self.queue,
                                      routing_key=routing_key)

    def start(self, app, *, loop):
        self._app = weakref.ref(app)()
        self._loop = weakref.ref(loop)()
        async def consume():
            # Need to reconnect because of potential forking affects
            await self.close()
            await self.connect(loop=loop)
            self._consumer_tag = (await self.channel.basic_consume(
                self.handle_request,
                queue_name=self.queue,
                no_ack=True)).get('consumer_tag')

        loop.run_until_complete(consume())

    def listen(self, *, loop):
        async def setup():

            await self.connect(loop=loop)
            await self.channel.queue_declare(queue_name=self.queue)
            await self.channel.basic_qos(prefetch_count=1, prefetch_size=0)

        loop.run_until_complete(setup())
        print('-- Listening for rabbitmq messages on queue {} --'
              .format(self.queue))

    async def connect(self, loop=None):
        self._transport, self._protocol = await aioamqp.connect(
            host=self.host,
            port=self.port,
            virtualhost=self.virtualhost,
            login=self.username,
            password=self.password,
            ssl=self.ssl,
            verify_ssl=self.verify_ssl,
            loop=loop
        )
        self.channel = await self._protocol.channel()

    async def close(self):
        await self._protocol.close()
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
        route = envelope.routing_key
        print(route)
        headers = properties.headers or {}
        query = headers.pop('query', '').lstrip('?')
        headers['content-type'] = properties.content_type
        headers['content-encoding'] = properties.content_encoding
        correlation_id = properties.correlation_id
        reply_to = properties.reply_to
        method = properties.type

        request = Request(
            headers=headers,
            path=route,
            correlation_id=correlation_id,
            method=method,
            query_string=query,
            body=body,
        )

        response = await self._app.handle_request(request)
        if not reply_to:
            # nowhere to reply. No point it trying to send a response
            return

        response.headers['Status'] = str(response.status.value)

        properties = {
            'correlation_id': response.correlation_id,
            'headers': response.headers,
            'content_type': response.content_type
        }
        await channel.basic_publish(response.data, '', reply_to,
                                    properties=properties)
        self._counter -= 1

    def shutdown(self, *, loop):
        loop.run_until_complete(self.channel.basic_cancel(self._consumer_tag))
        async def finish_tasks():
            while self._counter > 0:
                await asyncio.sleep(1)
        loop.run_until_complete(finish_tasks())
        loop.run_until_complete(self.close())


