import pytest
from waspy.router import Methods
from waspy.transports.rabbitmqtransport import parse_url_to_topic


@pytest.mark.parametrize("url,expected_topic", [
    ((Methods.GET, '/single'), "get.single"),
    ((Methods.GET, '/double/double'), "get.double.double"),
    ((Methods.GET, '/something/static/and/long'), "get.something.static.and.long"),
    ((Methods.GET, '/single/{id}'), "get.single.*"),
    ((Methods.GET, '/foo/{fooid}/bar/{barid}'), "get.foo.*.bar.*"),
    ((Methods.GET, '/foo/{fooid}/bar'), "get.foo.*.bar"),
    ((Methods.GET, '/foo/bar/baz/{id}'), "get.foo.bar.baz.*"),
    ((Methods.GET, '/multiple/{ids}/{in}/{a}/row'), "get.multiple.*.*.*.row"),
    ((Methods.GET, '/foo/{fooid}:action'), "get.foo.*"),
    ((Methods.GET, '/foo/{fooid}:action2'), "get.foo.*"),
    ((Methods.GET, '/test/test'), "get.test.test"),
])
def test_url_to_topic(url, expected_topic):
    assert parse_url_to_topic(*url) == expected_topic