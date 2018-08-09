from abc import ABC, abstractmethod
import json

from waspy.exceptions import ParseError


class ParserABC(ABC):
    """ Abstract Base Class for implementing encoding codecs """

    @property
    @abstractmethod
    def content_type(self) -> str:
        return ''

    @abstractmethod
    def encode(self, data) -> bytes:
        pass

    @abstractmethod
    def decode(self, data: bytes):
        pass


class JSONParser(ParserABC):
    """ The default parser for waspy. """
    content_type = 'application/json'

    def encode(self, data) -> bytes:
        return json.dumps(data)

    def decode(self, data: bytes):
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise ParseError("Invalid JSON")


parsers = {}
