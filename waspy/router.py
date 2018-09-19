import warnings
from contextlib import contextmanager
from http import HTTPStatus
from typing import Callable, Union
from enum import Enum

from .exceptions import ResponseError

"""
The below constant is special key in the router dictionary that determines an
id section of the url. The / character is the only character that
can't possibly be used in a url path or id, since it is the path delimiter.
Therefore, there are '/' characters in the key, so that it can never 
accidentally be overridden.

p.s. '_id' is to make the dictionary slightly more readable when debugging
"""
ID_KEY = '/_id/'


class NotAValidURLError(Exception):
    """ When a url path syntax is not valid """


class Methods(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    OPTIONS = 'OPTIONS'
    PATCH = 'PATCH'
    HEAD = 'HEAD'
    PUBLISH = 'PUBLISH'  # NOT VALID HTTP METHOD


async def _send_404(request):
    raise ResponseError(status=HTTPStatus.NOT_FOUND)


async def _send_405(request):
    raise ResponseError(status=HTTPStatus.METHOD_NOT_ALLOWED)


class Router:
    def __init__(self):
        self._routes = {}
        """
        Routes looks like:
        {path_section1: {path_section2: {method: (handler, params)}}}
                before startup and
        {path_section1: {papath_section2 {method: (wrapped, handler, params)}}
                after startup
        """
        self._static_routes = {}
        """
        Static routes are just simple d[url][method] lookups and skip
        middlewares
        """
        self.options_handler = None

        self.handle_404 = _send_404  # the 404 route will skip middlewares
        self.handle_405 = _send_405  # the 405 handler will skip middleware

        self._prefix = ''

        # A list of tuples (method, url)
        self.urls = []

    def _get_and_wrap_routes(self, _d=None):
        if _d is None:
            _d = self._routes
        for key, value in _d.items():
            # if value is a dictionary, keep going
            # if value is a tuple, then wrap it!
            if isinstance(value, dict):
                yield from self._get_and_wrap_routes(_d=value)
            else:
                handler, params = value
                wrapped = yield handler
                _d[key] = (wrapped, handler, params)

    def get_handler_for_request(self, request):
        method = request.method
        path = request.path
        route = path.strip('/')
        if method == Methods.OPTIONS and self.options_handler is not None:
            # Is this an OPTION and do we have a generic options handler?
            request._handler = self.options_handler
            return self.options_handler

        try:
            return self._static_routes[route][method]
        except KeyError:
            # not in static routes
            pass

        d = self._routes
        params = []
        raw_path_string = '/'
        is_a_path = False
        try:
            for portion in route.split('/'):
                sub = d.get(portion, None)
                if sub is None:  # must be an ID field
                    key = ID_KEY
                    param = portion
                    if ':' in portion:
                        param, action = portion.split(':', 1)
                        key += ':' + action

                    sub = d[key]
                    params.append(param)
                    raw_path_string += '*/'
                else:
                    raw_path_string += portion + '/'
                d = sub
            if any(isinstance(key, Methods) for key in d):
                is_a_path = True
            wrapped, handler, keys = d[method]
        except KeyError:
            if is_a_path:
                request._handler = self.handle_405
                return self.handle_405
            # No handler for given route
            request._handler = self.handle_404
            return self.handle_404
        assert len(keys) == len(params)
        for key, param in zip(keys, params):
            request.path_params[key] = param
        request._handler = handler
        request._raw_path = raw_path_string
        return wrapped

    def add_static_route(self, method: Union[str, Methods], route: str, handler: Callable,
                         skip_middleware=False):
        """
        Adds a static route. A static route is a special route that
        doesnt follow any of the normal rules, and never has any path
        parameters.
        Ideally, this is used for non-public facing endpoints such as
        "/healthcheck", or "/stats" or something of that nature.

        All static routes SKIP middlewares
        """
        if isinstance(method, str):
            method = Methods(method.upper())
        route = self._prefix + route
        route = route.strip('/')
        if route not in self._static_routes:
            self._static_routes[route] = {}
        self._static_routes[route][method] = handler

    def add_route(self, method: Union[str, Methods], route: str, handler: Callable):
        if isinstance(method, str):
            method = Methods(method.upper())

        route = self._prefix + route
        route = route.strip('/')
        self.urls.append((method, route))
        d = self._routes
        params = []
        for portion in route.split('/'):
            if portion.startswith('{') and '}' in portion:
                sections = portion.lstrip('{').split('}', maxsplit=1)
                params.append(sections[0])
                key = ID_KEY
                if sections[1]:
                    if not sections[1].startswith(':'):
                        raise NotAValidURLError(
                            'Cant have an id mixed with '
                            'a static word without a colon')
                    key += sections[1]

            else:
                key = portion
            if key not in d:
                d[key] = {}
            d = d[key]
        if method in d:
            raise ValueError(f"Duplicate route exists {method}")
        d[method] = handler, params

    def get(self, route: str, handler: Callable):
        self.add_route(Methods.GET, route, handler)

    def post(self, route: str, handler: Callable):
        self.add_route(Methods.POST, route, handler)

    def put(self, route: str, handler: Callable):
        self.add_route(Methods.PUT, route, handler)

    def patch(self, route: str, handler: Callable):
        self.add_route(Methods.PATCH, route, handler)

    def delete(self, route: str, handler: Callable):
        self.add_route(Methods.DELETE, route, handler)

    def head(self, route: str, handler: Callable):
        self.add_route(Methods.HEAD, route, handler)

    def options(self, route: str, handler: Callable):
        self.add_route(Methods.OPTIONS, route, handler)

    def add_get(self, route: str, handler: Callable):
        warnings.warn("add_get is deprecated, use get instead", DeprecationWarning)
        self.add_route(Methods.GET, route, handler)

    def add_post(self, route: str, handler: Callable):
        warnings.warn("add_post is deprecated, use post instead", DeprecationWarning)
        self.add_route(Methods.POST, route, handler)

    def add_put(self, route: str, handler: Callable):
        warnings.warn("add_put is deprecated, use put instead", DeprecationWarning)
        self.add_route(Methods.PUT, route, handler)

    def add_delete(self, route: str, handler: Callable):
        warnings.warn("add_delete is deprecated, use delete instead", DeprecationWarning)
        self.add_route(Methods.DELETE, route, handler)

    def add_patch(self, route: str, handler: Callable):
        warnings.warn("add_patch is deprecated, use patch instead", DeprecationWarning)
        self.add_route(Methods.PATCH, route, handler)

    def add_head(self, route: str, handler: Callable):
        warnings.warn("add_head is deprecated, use head instead", DeprecationWarning)
        self.add_route(Methods.HEAD, route, handler)

    def add_options(self, route: str, handler: Callable):
        warnings.warn("add_options is deprecated, use options instead", DeprecationWarning)
        self.add_route(Methods.OPTIONS, route, handler)

    def add_generic_options_handler(self, handler: Callable):
        """
        Add a handler for all options requests. This WILL bypass middlewares
        """
        self.options_handler = handler

    @contextmanager
    def prefix(self, prefix):
        """
        Adds a prefix to routes contained within.
        """
        original_prefix = self._prefix
        self._prefix += prefix
        yield self
        self._prefix = original_prefix


