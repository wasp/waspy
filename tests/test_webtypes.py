from waspy import webtypes


def test_query_params_simple():
    query_string = 'hello=world&foo=bar'
    query = webtypes.QueryParams.from_string(query_string)
    result = str(query)
    assert 'hello=world' in result
    assert 'foo=bar' in result
    assert '&' in result


def test_query_params_multiple():
    query_string = 'hello=world&foo=bar&hello=there'
    query = webtypes.QueryParams.from_string(query_string)
    result = str(query)
    assert 'hello=world' in result
    assert 'hello=there' in result
    assert 'foo=bar' in result
    assert result.count('&') == 2


def test_cookie_parsing():
    cookie = '__context=eyJTTFQiOiIxNDY0OTAxMjY3NzIyMzg; _numpgs=8; _numsess=2; intercom-id-h=e969; intercom-session-h=R0Y4ee; test1="abc"'
    r = webtypes.Request(headers={'cookie': cookie})
    assert r.cookies['test1'] == 'abc'


