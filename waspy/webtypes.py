import json
import warnings
from collections import defaultdict
from urllib import parse
from aenum import extend_enum

from waspy import exceptions
from waspy.parser import parsers
from .router import Methods
from http import HTTPStatus, cookies

extend_enum(HTTPStatus, 'INVALID_REQUEST', (430, 'Invalid Request',
                                            'Request was syntactically sound, '
                                            'but failed validation rules'))


class QueryParams:
    """
    A dictionary that stores multiple values per key.

    this has all the normal dictionary methods, and works as normal but does
    not override a key when `add` is used, and also has `getall`
    """
    __slots__ = ['mappings']

    @classmethod
    def from_string(cls, string):
        query_params = QueryParams()
        qs = parse.parse_qsl(string)
        for k, v in qs:
            query_params.add(k, v)

        return query_params

    def __init__(self):
        self.mappings = defaultdict(list)

    def get(self, name, default=None):
        return self.mappings.get(name, [default])[0]

    def getall(self, name, default=None):
        return self.mappings.get(name, default)

    def __getitem__(self, key):
        try:
            return self.mappings.__getitem__(key)[0]
        except IndexError:
            raise KeyError('Invalid Key: {key}'.format(key))

    def __setitem__(self, key, value):
        raise TypeError('MultiDict does not support item assignment. '
                        'Use .add(k, v) instead.')

    def add(self, name, value):
        self.mappings[name].append(value)

    def __str__(self):
        return parse.urlencode(self.mappings, doseq=True)


class Request:
    def __init__(self, headers: dict = None,
                 path: str = None, correlation_id: str = None,
                 method: str = None, query_string: str = None,
                 body: bytes=None, content_type=None):

        if not headers:
            headers = {}
        if not method:
            method = 'GET'
        self._method = None
        self.headers = headers
        self.path = path
        self.correlation_id = correlation_id
        self.method = method  # this is a property setter
        self.query_string = query_string
        self._query_params = None
        self.body = body
        self.path_params = {}
        self._handler = None
        self.app = None
        self.parser = None
        self.content_type = content_type
        self._data = None
        self._cookies = None

    @property
    def method(self):
        return self._method

    @method.setter
    def method(self, value):
        if isinstance(value, str):
            value = Methods(value.upper())
        self._method = value

    @property
    def path_qs(self):
        # the path + the query string
        query = '?' + self.query_string if self.query_string else ''
        return self.path + query

    @property
    def cookies(self) -> dict:
        if self._cookies is None:
            self._cookies = {}
            raw = self.headers.get('cookie', None)
            if raw:
                cookie_manager = cookies.SimpleCookie(raw)
                self._cookies = {i: cookie_manager[i].value for i in cookie_manager}
        return self._cookies

    @property
    def query(self) -> QueryParams:
        # parse query string into a dictionary
        if not self._query_params:
            self._query_params = QueryParams.from_string(self.query_string)
        return self._query_params

    def json(self) -> dict:
        warnings.warn('Use request.data() instead')
        return self.data()

    def data(self) -> dict:
        if not self._data:
            if not self.parser:
                if not self.content_type:
                    self.content_type = self.app.default_content_type
                self.parser = parsers.get(self.content_type)
                if not self.parser:
                    raise exceptions.UnsupportedMediaType(self.content_type)
            # convert body into a dict using the matching content_type
            self._data = self.parser.decode(self.body)
        return self._data

    def __str__(self):
        query = '?' + self.query_string if self.query_string else ''
        return('<Request({method} {path}{query})@{id}>'
               .format(method=self.method, path=self.path,
                       query=query, id=id(self)))

    def __repr__(self):
        return (f'Request(headers={repr(self.headers)}, path={repr(self.path)}, '
                f'correlation_id={self.correlation_id}, method={repr(self.method)}, '
                f'query_string={self.query_string}, body={self.body}, '
                f'content_type={self.content_type})')


class Response:
    def __init__(self, headers=None, correlation_id=None,
                 body=None, status=HTTPStatus.OK,
                 content_type=None, meta: dict=None):
        """
        Response object
        :param headers:
        :param correlation_id:
        :param body: message body
        :param status: status code
        :param content_type:
        :param meta: Extra context information.
            Not to be returned through transport
        """
        if not headers:
            headers = dict()
        if isinstance(status, int):  # convert to enum
            status = HTTPStatus(status)
        if meta is None:
            meta = {}
        self.headers = headers
        self.correlation_id = correlation_id
        self.body = body
        self.status = status
        self.content_type = content_type
        self.meta = meta
        self.app = None
        self.parser = None
        self._data = None
        self._json = None

    def __str__(self):
        return('<Response({status})@{id}>'
               .format(status=self.status, id=id(self)))

    @property
    def data(self):
        if self._data is None and self.body:
            if not self.parser:
                if not self.content_type and self.app.default_content_type:
                    self.content_type = self.app.default_content_type
                self.parser = parsers.get(self.content_type)
                if not self.parser:
                    raise exceptions.UnsupportedMediaType(self.content_type)
            self._data = self.parser.encode(self.body)
            if isinstance(self._data, str):
                self._data = self._data.encode()
        return self._data

    def json(self) -> dict:
        """
        Used for client response
        """
        if self.body is None:
            self._json = {}
        try:
            self._json = json.loads(self.body.decode())
        except json.JSONDecodeError as ex:
            raise exceptions.ParseError("Invalid JSON") from ex
        return self._json
