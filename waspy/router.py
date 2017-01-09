from enum import Enum

from waspy import webtypes


class NonRESTfulURLError(NotImplementedError):
    """ URL provided is not restful. """


class Methods(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    OPTIONS = 'OPTIONS'
    PATCH = 'PATCH'
    HEAD = 'HEAD'


def _parameterize_path(path):
    path_parts = path.split('.')

    params = []
    on_id_segment = False
    key = ''
    for part in path_parts:
        if on_id_segment:
            # this part is a resource id
            key += '.*'
            params.append(part)
        else:
            # this part is a resource name
            key += '.' + part
        on_id_segment = not on_id_segment
    return key, params


async def _send_404(request):
    raise webtypes.ResponseError(status=404)


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

    def _prepare_route(self, route):
        route = route.replace('/', '.').lstrip('.')
        key, params = _parameterize_path(route)

        # Check that route is RESTful
        for p in params:
            if (not p.startswith(':') or
                    (not p.startswith('{') and p.endswith('}'))):
                # Param is not an id parameter
                raise NonRESTfulURLError('Path variable expected in url, '
                                         'instead got {}')
        if ':' in key or '{' in key:
            raise NonRESTfulURLError('Got a path variable in URL when a '
                                     'resource name was expected')

        params = [p.strip(':').strip('{}') for p in params]
        return key, params

    def get_handler_for_request(self, request):
        method = request.method
        path = request.path
        route = path.lstrip('/').replace('/', '.')
        if method == Methods.OPTIONS and self.options_handler is not None:
            # Is this an OPTSION and do we have a generic options handler?
            request._handler = self.options_handler
            return self.options_handler

        try:
            return self._static_routes[route][method]
        except KeyError:
            # not in static routes
            pass

        d = self._routes
        params = []
        try:
            for portion in route.split('.'):
                sub = d.get(portion, None)
                if sub is None:
                    sub = d['_id']
                    params.append(portion)
                d = sub
            wrapped, handler, keys = d[method]
        except KeyError:
            # No handler for given route
            request._handler = self.handle_404
            return self.handle_404
        assert len(keys) == len(params)
        for key, param in zip(keys, params):
            request.path_params[key] = param
        request._handler = handler
        return wrapped

    def add_static_route(self, method: str, route: str, handler: callable,
                         skip_middleware=False):
        """
        Adds a static route. A static route is a special route that
        doesnt follow any of the normal rules, and never has any path
        parameters.
        Ideally, this is used for non-public facing endpoints such as
        "/healthcheck", or "/stats" or something of that nature.

        All static routes SKIP middlewares
        """
        if not isinstance(method, Methods):
            method = Methods(method.upper())
        route = route.lstrip('/').replace('/', '.')
        if route not in self._static_routes:
            self._static_routes[route] = {}
        self._static_routes[route][method] = handler

    def add_route(self, method: str, route: str, handler: callable):
        if not isinstance(method, Methods):
            method = Methods(method.upper())

        route = route.replace('/', '.').lstrip('.')
        d = self._routes
        params = []
        for portion in route.split('.'):
            if (portion.startswith(':') or
                    (portion.startswith('{') and portion.endswith('}'))):
                params.append(portion.strip(':').strip('{}'))
                key = '_id'
            else:
                key = portion
            if key not in d:
                d[key] = {}
            d = d[key]

        d[method] = handler, params

    def add_get(self, route: str, handler: callable):
        self.add_route(Methods.GET, route, handler)

    def add_post(self, route: str, handler: callable):
        self.add_route(Methods.POST, route, handler)

    def add_put(self, route: str, handler: callable):
        self.add_route(Methods.PUT, route, handler)

    def add_delete(self, route: str, handler: callable):
        self.add_route(Methods.DELETE, route, handler)

    def add_patch(self, route: str, handler: callable):
        self.add_route(Methods.PATCH, route, handler)

    def add_head(self, route: str, handler: callable):
        self.add_route(Methods.HEAD, route, handler)

    def add_options(self, route: str, handler: callable):
        self.add_route(Methods.OPTIONS, route, handler)

    def add_generic_options_handler(self, handler: callable):
        """
        Add a handler for all options requests. This WILL bypass middlewares
        """
        self.options_handler = handler
