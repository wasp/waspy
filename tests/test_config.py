import pytest
import io
import yaml

from waspy.configuration import Config, ConfigError


@pytest.fixture
def config(monkeypatch):
    yaml_string = """

wasp:
  setting1: 1  # int
  foo: bar  # string

database:
  username: normal_user

  migration:
    username: migration_user

flat: true  # boolean
flat_with_underscores: hello
"""
    def my_load_config(self):
        self.default_options = yaml.load(io.StringIO(yaml_string))

    monkeypatch.setattr(Config, '_load_config', my_load_config)
    config_ = Config()
    config_.load()
    return config_


def test_get_config_file(config):
    assert config['wasp']['foo'] == 'bar'
    assert config['wasp']['setting1'] == 1


def test_get_file_subsection(config):
    assert config['database']['username'] == 'normal_user'
    assert config['database']['migration']['username'] == 'migration_user'


def test_get_file_flat(config):
    assert config['flat'] == True


def test_get_not_existing_flat(config):
    with pytest.raises(ConfigError):
        config['somesetting']


def test_get_not_existing_sub_section(config):
    with pytest.raises(ConfigError):
        config['database']['something']['final']


def test_get_env_var_with_no_default(config, monkeypatch):
    monkeypatch.setenv('DATABASE_MIGRATION_PASSWORD', '1234pass')
    assert config['database']['migration']['password'] == '1234pass'


def test_get_env_var_override(config, monkeypatch):
    monkeypatch.setenv('DATABASE_USERNAME', 'other_user')
    assert config['database']['username'] == 'other_user'


def test_get_int_from_env_var(config, monkeypatch):
    monkeypatch.setenv('WASP_SETTING1', '1')
    assert config['wasp']['setting1'] == 1


def test_get_bool_from_env_var(config, monkeypatch):
    monkeypatch.setenv('flat', 'true')
    assert config['flat'] == True


def test_get_flat_with_underscores(config):
    assert config['flat_with_underscores'] == 'hello'


def test_get_flat_with_underscores_envvar(config, monkeypatch):
    monkeypatch.setenv('FLAT_WITH_UNDERSCORES', 'blarg')
    assert config['flat_with_underscores'] == 'blarg'



