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
        {method: {path: (handler, params)}} before startup and
        {method: {path: (wrapped, handler, params)}} after startup
        """
        self._static_routes = {}
        """
        Static routes look similar to routes, but with only a handler, no tuple
        (before the app is started, they also include a boolean to whether
        they should be wrapped or not {method: {path: handler, True}})
        {method: {path: handler}}
        """
        self._no_wrap_static_routes = {}
        self.options_handler = None

        self.handle_404 = _send_404  # the 404 route will skip middlewares

    def _get_and_wrap_routes(self):
        for method, routes in self._routes.items():
            for path, t in routes.items():
                handler, params = t
                wrapped = yield handler
                routes[path] = (wrapped, handler, params)
        for method, routes in self._static_routes.items():
            for path, t in routes.items():
                handler, should_not_wrap = t
                if should_not_wrap:
                    wrapped = handler
                else:
                    wrapped = yield handler
                routes[path] = wrapped

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
            request._handler = self.options_handler
            return self.options_handler

        try:
            return self._static_routes[method][route]
        except KeyError:
            # not in static routes
            pass

        path, params = _parameterize_path(route)
        try:
            wrapped, handler, keys = self._routes[method][path]
        except KeyError:
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

        Set `skip_middleware` to true to bypass middlewares
        """
        if not isinstance(method, Methods):
            method = Methods(method.upper())
        if method not in self._static_routes:
            self._static_routes[method] = {}
        route = route.lstrip('/').replace('/', '.')
        self._static_routes[method][route] = handler, skip_middleware

    def add_route(self, method: str, route: str, handler: callable):
        if not isinstance(method, Methods):
            method = Methods(method.upper())
        if method not in self._routes:
            self._routes[method] = {}
        prepared_route, params = self._prepare_route(route)
        self._routes[method][prepared_route] = handler, params

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
