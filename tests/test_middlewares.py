import asyncio

from waspy import Application, Request, Response


def test_that_middleware_wrapping_works():
    async def middleware_a_factory(app, handler):
        async def middleware_a(request):
            request.a = 'a'
            return await handler(request)
        return middleware_a

    async def middleware_b_factory(app, handler):
        async def middleware_b(request):
            request.b = 'b'
            return await handler(request)
        return middleware_b

    async def handle(request):
        assert request.a == 'a'
        assert request.b == 'b'
        return 'c'

    request = Request(method='GET', path='/')
    app = Application(
        middlewares=(middleware_a_factory, middleware_b_factory))
    app.router.add_get('/', handle)
    coro = app._wrap_handlers()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(coro)
    handler = app.router.get_handler_for_request(request)
    assert handler != handle
    result = loop.run_until_complete(handler(request))
    result.app = app
    assert isinstance(result, Response)
    assert result.original_body == 'c'
