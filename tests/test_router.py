import pytest

from waspy import router



@pytest.mark.parametrize('test_input,expected_string,expected_params', [
    ('single', '.single', []),
    ('single.id', '.single.*', ['id']),
    ('foo.fooid.bar.barid', '.foo.*.bar.*', ['fooid', 'barid']),
    ('foo.fooid.bar', '.foo.*.bar', ['fooid']),
    ('trywith.:colon.bar.:bar', '.trywith.*.bar.*', [':colon', ':bar'])
])
def test_parameterize_path(test_input, expected_string, expected_params):
    path, params = router._parameterize_path(test_input)
    assert path == expected_string
    assert params == expected_params
