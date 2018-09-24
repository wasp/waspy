import json
from urllib import parse
import uuid
import warnings

import asyncio

from .webtypes import QueryParams, Request, Methods
from .ctx import request_context


class Client:
    """ Generic Client class for making a wasp client """
    __slots__ = ('transport',)

    def __init__(self, transport=None, **kwargs):
        if not transport:
            from waspy.transports import HTTPClientTransport
            transport = HTTPClientTransport(**kwargs)
        self.transport = transport

    def make_request(self, method, service, path, body=None,
                           query_params: QueryParams=None,
                           headers: dict=None,
                           correlation_id: str=None,
                           content_type: str='application/json',
                           context: Request=None,
                           timeout=30,
                           **kwargs) -> asyncio.coroutine:
        """
        Make a request to another service. If `context` is provided, then
        context and correlation will be pulled from the provided request
        object for you. This includes credentials, correlationid,
        and service-headers.

        :param method: GET/PUT/PATCH, etc.
        :param service: name of service
        :param path: request object path
        :param body: body of request
        :param query_params:
        :param headers:
        :param correlation_id:
        :param content_type:
        :param context: A request object from which a "child-request"
            will be made
        :param timeout: Time in seconds the client will wait befor raising
            an asyncio.TimeoutError
        :param kwargs: Just a place holder so transport specific options
            can be passed through
        :return:
        """
        if not isinstance(method, Methods):
            method = Methods(method.upper())
        if content_type == 'application/json' and isinstance(body, dict):
            body = json.dumps(body)
        if isinstance(query_params, dict):
            query_string = parse.urlencode(query_params)
        elif isinstance(query_params, QueryParams):
            query_string = str(query_params)
        else:
            query_string = ''
        headers = headers or {}

        ctx = request_context.get()
        if context:
            warnings.warn("Passing in a context to waspy client is deprecated. "
                          "Passed in context will be ignored", DeprecationWarning)

        if not correlation_id:
            correlation_id = ctx['correlation_id']

        headers = {**headers, **ctx['ctx_headers']}
        exchange = headers.get('x-ctx-exchange-override', None)
        if exchange:
            kwargs['exchange'] = exchange

        if isinstance(body, str):
            body = body.encode()
        response = asyncio.wait_for(
            self.transport.make_request(
                service, method.name, path, body=body, query=query_string,
                headers=headers, correlation_id=correlation_id,
                content_type=content_type, timeout=timeout, **kwargs),
            timeout=timeout)
        return response  # response is a coroutine that must be awaited

    def get(self, service, path, **kwargs):
        """ Make a get request (this returns a coroutine)"""
        return self.make_request(Methods.GET, service, path, **kwargs)

    def post(self, service, path, body, **kwargs):
        """ Make a post request (this returns a coroutine)"""
        return self.make_request(Methods.POST, service, path, body=body,
                                 **kwargs)

    def put(self, service, path, body, **kwargs):
        """ Make a put request (this returns a coroutine)"""
        return self.make_request(Methods.POST, service, path, body=body,
                                 **kwargs)

    def patch(self, service, path, body, **kwargs):
        """ Make a patche requests (this returns a coroutine)"""
        return self.make_request(Methods.PATCH, service, path, body=body,
                                 **kwargs)

    def delete(self, service, path, **kwargs):
        """ Make a delete requests (this returns a coroutine)"""
        return self.make_request(Methods.DELETE, service, path, **kwargs)
