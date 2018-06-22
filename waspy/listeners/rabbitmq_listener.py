import json

import aioamqp

from waspy.listeners.transport_listener_abc import TransportListenerABC
from waspy.transports.rabbitmqtransport import RabbitMQTransport


class RabbitMQTransportListener(TransportListenerABC):
    queue = ''
    exchange = ''
    routing_key = ''

    exchange_type = 'topic'
    declare_exchange = True
    declare_queue = True

    durable = True
    auto_delete = False
    exclusive = False
    no_wait = False
    prefetch_count = 1

    use_acks = True
    nack_on_error = True
    requeue_nacks = True

    json_payload = True

    def __init__(self, ):
        self.transport = None
        self.channel: aioamqp.channel.Channel = None

        self._consumer_tag = None
        self._bootstrapped = False

    async def set_channel(self, channel):
        self._bootstrapped = False
        if self.channel and self.channel.is_open:
            await self.transport.close_channel(self.channel)
        self.channel = channel
        await self._bootstrap_channel()

    def set_transport(self, transport: RabbitMQTransport):
        if not isinstance(transport, RabbitMQTransport):
            raise TypeError(
                "Invalid transport received. "\
                f"Expected {type(RabbitMQTransport)}, got type{transport}"
                )
        self.transport = transport
    
    async def start(self):
        if not self.channel:
            self.channel = await self.transport.create_channel()
        await self._bootstrap_channel()

        resp = await self.channel.basic_consume(
            self._handle_work,
            queue_name=self.queue,
            no_ack=not self.use_acks
        )
        self._consumer_tag = resp.get('consumer_tag')

    async def _handle_work(self, _, body, envelope, properties):
        if self.json_payload:
            body = json.loads(body)
        try:
            await self.handle_work(body, evelope=envelope, properties=properties)
        except Exception as e:
            if self.nack_on_error and self.use_acks:
                await self.channel.basic_client_nack(envelope.delivery_tag, requeue=self.requeue_nacks)
            raise e
        else:
            if self.use_acks:
                await self.channel.basic_client_ack(envelope.delivery_tag)

    async def exchange_declare(self):
        """ Override this method to change how a exchange is declared """
        await self.channel.exchange_declare(
            self.exchange,
            self.exchange_type,
            durable=self.durable,
            auto_delete=self.auto_delete,
            no_wait=self.no_wait,
        )

    async def queue_declare(self):
        """ Override this method to change how a queue is declared """ 
        await self.channel.queue_declare(
                self.queue,
                durable=self.durable,
                exclusive=self.exclusive,
                no_wait=self.no_wait
            )

    async def _bootstrap_channel(self):
        if self._bootstrapped:
            return
        self._bootstrapped = True
        await self.channel.basic_qos(prefetch_count=self.prefetch_count)
        if self.declare_queue:
            await self.queue_declare()
        if self.exchange:
            if self.declare_exchange:
                await self.exchange_declare()
            await self.channel.queue_bind(
                self.queue,
                self.exchange,
                self.routing_key,
            )

