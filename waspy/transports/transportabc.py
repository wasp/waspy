"""
A place for abstract transport base classes
"""
from abc import ABC, abstractmethod
from .. import webtypes


class ClientTransportABC(ABC):
    """Abstract Base Class for implementing client transports"""
    @abstractmethod
    async def make_request(self, service: str, method: str, path: str,
                           body: bytes=None, query: str=None,
                           headers: dict=None, correlation_id: str=None,
                           content_type: str=None,
                           timeout:int = 30,
                           **kwargs) -> webtypes.Response:
        """
        Method for actually making a request
        :param service: service to make request too
        :param method: HTTP method: GET/PUT/POST etc.
        :param path: routing path.
            Should support dots `foo.2.bars` or slashes `foo/2/bars`
        :param body: request body. Bytes-like object
        :param query: query string. Example: `foo=bar&cabbage=green`
        :param headers: Dictionary of headers
        :param correlation_id:
        :param content_type: example: `application/json`
        :param timeout: time to wait for response in seconds before getting
            an asyncio.TimeoutError
        :param kwargs: Should except **kwargs for compatability for
            other possible options on other transports
            (for example, http might need a `port` option)
        :return:
        """


class PubSubTransportABC(ABC):
    """ Abstract Base Class for implementing pubsub client transports"""


class TransportABC(ABC):
    """ Abstract Base Class for implementing server transports"""
    @abstractmethod
    def listen(self, *, loop, config):
        """This method is responsible for establishing a listening connection
        For example, in HTTP world this would mean acquiring a specific port,
        in a RabbitMQ world this would mean getting a connection and attaching
        to  a queue.
        """

    @abstractmethod
    async def start(self, request_handler: callable):
        """ This method does things needed before we run
        Like "listen" but you get the app object,
        and it happens after the fork. This is a corousine
        """

    def get_client(self):
        raise NotImplementedError

    @abstractmethod
    def shutdown(self):
        """ Signals that we are shutting down """


class WorkerTransportABC(ABC):
    """ Abstract Base Class for implementing worker transports """
    @abstractmethod
    def start(self):
        pass
