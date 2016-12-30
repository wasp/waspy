"""
A place for abstract transport base classes
"""
from abc import ABC, abstractmethod
from ..router import Router
from .. import webtypes


class ClientTransportABC(ABC):
    """Abstract Base Class for implementing client transports"""
    @abstractmethod
    async def make_request(self, service: str, method: str, path: str,
                           body: bytes=None, query: str=None,
                           headers: dict=None, correlation_id: str=None,
                           content_type: str=None,
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
        :param kwargs: Should except **kwargs for compatability for
            other possible options on other transports
            (for example, http might need a `port` option)
        :return:
        """


class TransportABC(ABC):
    """ Abstract Base Class for implementing server transports"""
    @abstractmethod
    def listen(self, *, loop):
        """This method is responsible for establishing a listening connection
        For example, in HTTP world this would mean acquiring a specific port,
        in a RabbitMQ world this would mean getting a connection and attaching
        to  a queue.
        """

    @abstractmethod
    def start(self, request_handler: callable, *, loop):
        """ This method does things needed before we run
        Like "listen" but you get the app object,
        and it happens after the fork
        """

    def get_client(self):
        raise NotImplementedError

    @abstractmethod
    def shutdown(self, *, loop):
        """ Allows you to close up shop and shut down gracefully"""
