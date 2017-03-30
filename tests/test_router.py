import pytest
from unittest.mock import Mock
from waspy.router import Router, Methods


@pytest.fixture
def router():
    router_ = Router()
    router_.add_get('/single', 1)
    router_.add_get('/double/double', 2)
    router_.add_get('/something/static/and/long', 3)
    router_.add_get('/single/{id}', 4)
    router_.add_get('/foo/{fooid}/bar/{barid}', 5)
    router_.add_get('/foo/{fooid}/bar', 6)
    router_.add_get('/foo/bar/baz/{id}', 7)
    router_.add_get('/multiple/{ids}/{in}/{a}/row', 8)
    router_.add_get('/foo/{fooid}:action', 9)
    router_.add_get('/foo/{fooid}:action2', 10)

    # now wrap all handlers with nothing
    handler_gen = router_._get_and_wrap_routes()

    try:
        handler = next(handler_gen)
        while True:
            handler = handler_gen.send(handler)
    except StopIteration:
        pass

    return router_


@pytest.mark.parametrize('path,expected_handler,expected_params', [
    ('/single', 1, []),
    ('/double/double', 2, []),
    ('/something/static/and/long', 3, []),
    ('/single/_id', 4, ['id']),
    ('/foo/_fooid/bar/_barid', 5, ['fooid', 'barid']),
    ('/foo/_fooid/bar', 6, ['fooid']),
    ('/foo/bar/baz/_id', 7, ['id']),
    ('/multiple/_ids/_in/_a/row', 8, ['ids', 'in', 'a']),
    ('/foo/_fooid:action', 9, ['fooid']),
    ('/foo/_fooid:action2', 10, ['fooid']),
])
def test_get_handler(path, expected_handler, expected_params, router):
    # Set up dummy request
    request = Mock()
    request.method = Methods.GET
    request.path = path
    request.path_params = {}

    wrapped_handler = router.get_handler_for_request(request)
    handler = request._handler
    assert handler == expected_handler
    for key in expected_params:
        assert key in request.path_params
        assert request.path_params[key] == '_' + key

