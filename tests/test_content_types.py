import json
from unittest.mock import MagicMock

import pytest

from waspy import Response
from waspy.exceptions import UnsupportedMediaType
from waspy.parser import JSONParser


@pytest.mark.parametrize("parsers,content_type,fail", [
    ([], 'application/json', True),
    ([JSONParser()], 'application/json', False),
    ([JSONParser()], 'application/x-yaml', True),
])
def test_content_types(parsers, content_type, fail, monkeypatch):
    app = MagicMock()
    app.default_content_type = 'application/json'
    p = {x.content_type: x for x in parsers}
    monkeypatch.setattr('waspy.webtypes.parsers', p)

    try:
        data = {'test': 'data'}
        r = Response(body=data, content_type=content_type)
        r.app = app
        r.raw_body
    except UnsupportedMediaType:
        assert fail
    else:
        assert not fail


def test_body_raw_body(monkeypatch):
    app = MagicMock()
    app.default_content_type = 'application/json'
    p = {'application/json': JSONParser()}
    monkeypatch.setattr('waspy.webtypes.parsers', p)

    # Test happy path
    original_body = {'test': 'original'}
    r = Response(body=original_body)
    r.app = app
    assert r.body == original_body
    assert r.raw_body == json.dumps(original_body).encode()

    # Test changing the body later
    new_body = {'test': 'new body'}
    r.body = new_body
    assert r.body == new_body
    assert r.raw_body == json.dumps(new_body).encode()
