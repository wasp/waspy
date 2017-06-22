from http import HTTPStatus

from .configuration import ConfigError
from .webtypes import Response, Request
from .router import Methods


class CORSHandler:
    __slots__ = ('allowed_origins', 'allowed_headers', 'allowed_methods')
    """
    Abstracts CORS things
    """
    def __init__(self, *, allowed_origins: set, allowed_headers: str,
                 allowed_methods: str):
        if len(allowed_origins) == 1:
            self.allowed_origins = allowed_origins.pop()
        else:
            self.allowed_origins = allowed_origins
        self.allowed_headers = allowed_headers
        self.allowed_methods = allowed_methods

    def add_cors_headers(self, request: Request, response: Response):
        if isinstance(self.allowed_origins, str):
            # only one origin
            result = self.allowed_origins

        elif request.headers.get('origin') in self.allowed_origins:
            result = request.headers.get('origin')

        else:
            result = 'none'

        response.headers['Access-Control-Allow-Origin'] = result
        response.headers['Access-Control-Allow-Credentials'] = 'true'

        if request.method == Methods.OPTIONS:
            if self.allowed_headers:
                response.headers['Access-Control-Allow-Headers'] = \
                    self.allowed_headers
            if self.allowed_methods:
                response.headers['Access-Control-Allow-Methods'] = \
                    self.allowed_methods

    async def options_handler(self, request):
        return Response(status=HTTPStatus.NO_CONTENT)

    @staticmethod
    def from_config(config):
        try:
            config['cors']['handle']
        except ConfigError:
            return None

        origins = config['cors']['allowed_origins']
        if not origins:  # if empty
            raise ValueError('Must have at least one cors.allowed_origins'
                             ' in your configuration.')

        origins = {origin.strip() for origin in origins.split(',')}

        try:
            headers = config['cors']['allowed_headers']
        except ConfigError:
            headers = ''

        try:
            methods = config['cors']['allowed_methods']
        except ConfigError:
            methods = ''

        return CORSHandler(allowed_origins=origins, allowed_headers=headers,
                           allowed_methods=methods)
