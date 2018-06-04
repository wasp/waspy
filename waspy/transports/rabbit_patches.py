""" This is ugly, but you do what you gotta do

So... on that note: Lets do some monkey patching!!
We need to support mandatory bit, and handle returned messages, but
aioamqp doesnt support it yet.
(follow https://github.com/Polyconseil/aioamqp/pull/158)

monkey patching _write_frame_awaiting_response fixes a waiter error.
(follow PR here: https://github.com/Polyconseil/aioamqp/pull/159)

"""
import io
import logging

import aioamqp
from aioamqp import frame as amqp_frame, channel
from aioamqp import constants as amqp_constants


logger = logging.getLogger(__name__)


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