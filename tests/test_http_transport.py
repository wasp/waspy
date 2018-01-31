from unittest import mock
from waspy.transports import httptransport
from waspy.webtypes import Request


def test_url_parsing_urldecode():
    transport = mock.Mock()
    transport.request = Request()
    transport._parent.prefix = ''

    transport.on_url = httptransport._HTTPServerProtocol.on_url

    transport.on_url(transport, b'/hello%2Bthere?title=%D0%BF%D1%80%D0%B0%D0%B2%D0%BE%D0%B2%D0%B0%D1%8F+%D0%B7%D0%B0%D1%89%D0%B8%D1%82%D0%B0')

    assert transport.request.path == '/hello+there'
    assert transport.request.query['title'] == 'правовая защита'


def test_url_parsing_double_path():
    transport = mock.Mock()
    transport.request = Request()
    transport._parent.prefix = ''

    transport.on_url = httptransport._HTTPServerProtocol.on_url

    transport.on_url(transport, b'//hello')

    assert transport.request.path == '/hello'


def test_url_parsing_strip_prefix():
    transport = mock.Mock()
    transport.request = Request()
    transport._parent.prefix = '/api'

    transport.on_url = httptransport._HTTPServerProtocol.on_url

    transport.on_url(transport, b'/api/hello')

    assert transport.request.path == '/hello'