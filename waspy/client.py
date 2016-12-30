import json
from urllib import parse
import uuid

from .webtypes import QueryParams


class Client:
    """ Generic Client class for making a wasp client """
    __slots__ = ('transport',)

    def __init__(self, transport=None, **kwargs):
        if not transport:
            from waspy.transports import HTTPClientTransport
            transport = HTTPClientTransport(**kwargs)
        self.transport = transport

    async def make_request(self, method, service, path, body=None,
                           query_params=None, headers=None,
                           correlation_id=None,
                           content_type='application/json', **kwargs):
        """ Make a request"""
        if content_type == 'application/json' and isinstance(body, dict):
            body = json.dumps(body)
        if isinstance(query_params, dict):
            query_string = parse.urlencode(query_params)
        elif isinstance(query_params, QueryParams):
            query_string = str(QueryParams)
        else:
            query_string = ''
        if not correlation_id:
            correlation_id = uuid.uuid4()
        if isinstance(body, str):
            body = body.encode()
        response = await self.transport.make_request(
            service, method, path, body=body, query=query_string,
            headers=headers, correlation_id=correlation_id,
            content_type=content_type)
        return response

    async def get(self, service, path):
        """ Make a get request """

    async def post(self, service, path, body):
        """ Make a post request """

    async def put(self, service, path, body):
        """ Make a put request """

    async def patch(self, service, path, body):
        """ Make a patche requests """

    async def delete(self, service, path):
        """ Make a delete requests """
