import pytest
from unittest.mock import Mock
from waspy.router import Router, Methods


@pytest.fixture
def router():
    router_ = Router()
    router_.get('/single', 1)
    router_.get('/double/double', 2)
    router_.get('/something/static/and/long', 3)
    router_.get('/single/{id}', 4)
    router_.get('/foo/{fooid}/bar/{barid}', 5)
    router_.get('/foo/{fooid}/bar', 6)
    router_.get('/foo/bar/baz/{id}', 7)
    router_.get('/multiple/{ids}/{in}/{a}/row', 8)
    router_.get('/foo/{fooid}:action', 9)
    router_.get('/foo/{fooid}:action2', 10)

    with router_.prefix('/test'):
        router_.get('/test', 11)

    with router_.prefix('/nest-1'):
        with router_.prefix('/nest-2'):
            with router_.prefix('/nest-3/{nest3id}'):
                with router_.prefix('/nest-4'):
                    router_.get('/nest-4-get', 4)
                    with router_.prefix('/nest-5'):
                        router_.get('/nest-5-get', 5)
                    router_.get('/nest-4-get-2', 42)

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
    ('/test/test', 11, []),
    ('/nest-1/nest-2/nest-3/_nest3id/nest-4/nest-4-get', 4, ['nest3id']),
    ('/nest-1/nest-2/nest-3/_nest3id/nest-4/nest-4-get-2', 42, ['nest3id']),
    ('/nest-1/nest-2/nest-3/_nest3id/nest-4/nest-5/nest-5-get', 5, ['nest3id'])
])
def test_get_handler(path, expected_handler, expected_params, router):
    # Set up dummy request
    request = Mock()
    request.method = Methods.GET
    request.path = path
    request.path_params = {}

    wrapped_handler = router.get_handler_for_request(request)
    handler = request._handler
    assert expected_handler == handler
    for key in expected_params:
        assert key in request.path_params
        assert request.path_params[key] == '_' + key


def test_duplicate_handler():
    router_ = Router()
    router_.get('/test/path', 5)

    with pytest.raises(ValueError):
        router_.get('/test/path', 6)

    router_.get('/test/path/{param}', 5)

def test_urls(router):
    urls = [
        (Methods.GET, '/single'),
        (Methods.GET, '/double/double'),
        (Methods.GET, '/something/static/and/long'),
        (Methods.GET, '/single/{id}'),
        (Methods.GET, '/foo/{fooid}/bar/{barid}'),
        (Methods.GET, '/foo/{fooid}/bar'),
        (Methods.GET, '/foo/bar/baz/{id}'),
        (Methods.GET, '/multiple/{ids}/{in}/{a}/row'),
        (Methods.GET, '/foo/{fooid}:action'),
        (Methods.GET, '/foo/{fooid}:action2'),
        (Methods.GET, '/test/test'),
        (Methods.GET, '/nest-1/nest-2/nest-3/{nest3id}/nest-4/nest-4-get'),
        (Methods.GET, '/nest-1/nest-2/nest-3/{nest3id}/nest-4/nest-5/nest-5-get'),
        (Methods.GET, '/nest-1/nest-2/nest-3/{nest3id}/nest-4/nest-4-get-2')
    ]
    for idx, url in enumerate(urls):
        assert url == router.urls[idx]
