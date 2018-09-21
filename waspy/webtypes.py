from collections import defaultdict
from urllib import parse
from http import HTTPStatus, cookies
import uuid

from aenum import extend_enum

from waspy import exceptions
from waspy.parser import parsers
from .router import Methods

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


class Parseable:
    def __init__(self, *args, content_type=None, body=None, **kwargs):
        self._parser = None
        self.app = None
        self.original_body = body
        self._body = None
        self._raw_body = None

        self._content_type = None
        self.content_type = content_type
        self.ignore_content_type = kwargs.get('ignore_content_type', False)

    @property
    def content_type(self):
        if self._content_type:
            return self._content_type
        if self.app:
            return self.app.default_content_type

    @content_type.setter
    def content_type(self, value):
        if value:
            # Throw away charset for now. We will have to figure this out later.
            self._content_type = value.split(';')[0]

    @property
    def parser(self):
        if not self._parser:
            self._parser = parsers.get(self.content_type)
            if not self._parser and not self.ignore_content_type:
                raise exceptions.UnsupportedMediaType(self.content_type)
        return self._parser

    @property
    def body(self) -> dict:
        """ Decoded Body """
        if self.ignore_content_type:
            return self.original_body
        if self._body is None and self.original_body is not None:
            if isinstance(self.original_body, bytes):
                self._body = self.parser.decode(self.original_body)
            else:
                self._body = self.original_body
        return self._body

    @body.setter
    def body(self, value):
        if isinstance(value, bytes):
            # Transports sometimes set the value after the response is created
            # Setting it to the original_body allows for lazy parsing
            self.original_body = value
            # Reset body and raw_body
            self._raw_body = None
            self._body = None
        elif isinstance(value, dict):
            self._body = value
            # Reset the raw_body
            self.original_body = value
            self._raw_body = None

    @property
    def raw_body(self) -> bytes:
        """ Encoded Body """
        if self._raw_body is None and self.original_body is not None:
            if isinstance(self.original_body, dict):
                self._raw_body = self.parser.encode(self.original_body)
                if isinstance(self._raw_body, str):
                    self._raw_body = self._raw_body.encode()
            elif isinstance(self.original_body, str):
                self._raw_body = self.original_body.encode()
            elif isinstance(self.original_body, bytes):
                self._raw_body = self.original_body
            else:
                self._raw_body = self.parser.encode(self.original_body)
                if isinstance(self._raw_body, str):
                    self._raw_body = self._raw_body.encode()
        return self._raw_body

    def json(self) -> dict:
        """ Simply an alias now for getting the decoded body """
        return self.body


class Request(Parseable):
    def __init__(self, headers: dict = None,
                 path: str = None, correlation_id: str = None,
                 method: str = None, query_string: str = None,
                 body: bytes=None, content_type=None):

        super().__init__(
            headers=headers, path=path, correlation_id=correlation_id, method=method,
            query_string=query_string, body=body, content_type=content_type)

        if not headers:
            headers = {}
        if not method:
            method = 'GET'
        self._method = None
        self.headers = headers
        self.path = path
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.method = method  # this is a property setter
        self.query_string = query_string
        self._query_params = None
        self.path_params = {}
        self._handler = None
        self.app = None
        self.content_type = content_type
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


class Response(Parseable):
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
        super().__init__(
            headers=headers, correlation_id=correlation_id,
            body=body, status=status, content_type=content_type, meta=meta)
        if not headers:
            headers = dict()
        if isinstance(status, int):  # convert to enum
            status = HTTPStatus(status)
        if meta is None:
            meta = {}
        self.headers = headers
        self.correlation_id = correlation_id
        self.original_body = body
        self.status = status
        self.meta = meta
        self.app = None
        self._body = None
        self._raw_body = None

    def __str__(self):
        return('<Response({status})@{id}>'
               .format(status=self.status, id=id(self)))
