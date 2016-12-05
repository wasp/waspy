
from .transportabc import TransportABC


class RabbitMQTransport(TransportABC):
    def run(self, app, *, loop):
        pass

    def listen(self, *, loop):
        pass

