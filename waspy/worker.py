from typing import Union, List, Iterable
from .transports.transportabc import WorkerTransportABC
from .transports.rabbitmqtransport import RabbitMQWorkerTransport


class Task:
    pass


class Worker:
    def __init__(self,
                 transport: Union[WorkerTransportABC,
                                  Iterable[WorkerTransportABC]]):
        self.transport = transport

    def run(self):
        if self.transport is None:
            pass
