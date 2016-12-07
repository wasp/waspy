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
    async def start(self, app, *, loop):
        """ This method does things needed before we run
        Like "listen" but you get the app object,
        and it happens after the fork
        """
        pass

    @abstractmethod
    async def shutdown(self, *, loop):
        pass
