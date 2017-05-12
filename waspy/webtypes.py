import json
from collections import defaultdict
from urllib import parse
from aenum import extend_enum
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
                 body: bytes=None, content_type='application/json'):

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
        self.content_type = content_type
        self._json = None
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
        if not self._json:
            # convert body into a json dict
            try:
                self._json = json.loads(self.body.decode())
            except json.JSONDecodeError as ex:
                raise JSONDecodeError from ex
        return self._json

    def __str__(self):
        query = '?' + self.query_string if self.query_string else ''
        return('<Request({method} {path}{query})@{id}>'
               .format(method=self.method, path=self.path,
                       query=query, id=id(self)))

class Response:
    def __init__(self, headers=None, correlation_id=None,
                 body=None, status=HTTPStatus.OK,
                 content_type='application/json', meta: dict=None):
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
        self._data = None
        self._json = None

    def __str__(self):
        return('<Response({status})@{id}>'
               .format(status=self.status, id=id(self)))

    @property
    def data(self):
        if self._data is None and self.body:
            if (self.content_type == 'application/json' and
                    isinstance(self.body, dict)):
                self._data = json.dumps(self.body)
            else:
                self._data = self.body
            if isinstance(self._data, str):
                self._data = self._data.encode()
        return self._data

    def json(self) -> dict:
        """
        Used for client response
        """
        if self.body is None:
            self._json = {}
        elif not self._json:
            # convert body into a json dict
            try:
                self._json = json.loads(self.body.decode())
            except json.JSONDecodeError as ex:
                raise JSONDecodeError from ex
        return self._json


class ResponseError(Exception):
    def __init__(self, message=None, status=None, *, body=None, headers=None,
                 correlation_id=None, reason=None, log=False):
        super().__init__(message)
        self.message = message
        if hasattr(self, 'status') and status is None:
            status = self.status
        if hasattr(self, 'body') and body is None:
            body = self.body
        if hasattr(self, 'reason') and reason is None:
            reason = self.reason
        if hasattr(self, 'log') and log == False:
            log = self.log
        if reason and not body:
            body = {'reason': reason}
        self.response = Response(status=status, body=body, headers=headers,
                                 correlation_id=correlation_id)
        self.log = log


class JSONDecodeError(ResponseError):
    status = 400
    reason = 'Invalid Json'
