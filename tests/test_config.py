import pytest
import toml

from waspy.configuration import Config, ConfigError
@pytest.fixture
def config(monkeypatch):
    toml_string = """
flat = true  # boolean

[wasp]
setting1 = 1  # int
foo = 'bar'  # string

[database]
username = 'normal_user'

  [database.migration]
  username = 'migration_user'
"""
    def my_load_config(self):
        return toml.loads(toml_string)

    monkeypatch.setattr(Config, 'load_config', my_load_config)
    return Config()


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


