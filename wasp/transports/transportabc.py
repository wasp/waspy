from abc import ABC, abstractmethod


class TransportABC(ABC):

    @abstractmethod
    def listen(self, *, loop):
        """This method is responsible for establishing a listening connection
        For example, in HTTP world this would mean acquiring a specific port,
        in a Rabbitmq world this would mean getting a connection and attaching
        to  a queue.
        """
        pass

    @abstractmethod
    async def run(self, app, *, loop):
        """ This method runs the app - listening for
        and receiving connections"""
        pass
