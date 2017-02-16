import os
import yaml

CONFIG_LOCATION = os.getenv('WASPY_CONFIG_LOCATION')


class ConfigError(KeyError):
    """ Raised when a requested configuration can not be found """
    def __init__(self, config_name, env_var):
        super().__init__("""\
No configuration found for "{}". \
Add the environment variable {} or add \
the key to your config.yaml file.\
""".format(config_name, env_var))

NO_CONFIG_LOCATION_ERROR_MESSAGE = """
No config file specified. \
You can use `app.config.from_file(file_location)` or set a location using \
the environment variable "WASPY_CONFIG_LOCATION".\
"""

CONFIG_NOT_YET_LOADED_ERROR_MESSAGE = """
Configuration file not yet loaded. \
You should use `[app.]config.from_file(location)` or `[app.]config.load` \
before trying to access a configuration value.\
"""


class Config:
    """ load configuration from envvar or config file
        You can get settings from environment variables or a config.yaml file
        Environment variables have a higher precedence over the config file

        Use `config['section']['subsection']['key']` to get the value
        SECTION_SUBSECTION_KEY from environment variables or
        section.subsection.key from a yaml file
        (usually written:
            [section.subsection]
            key = value
        in a yaml file)
    """
    def __init__(self, _basename=None, _defaults=None):
        self.default_options = _defaults
        self.basename = _basename

    def from_file(self, location):
        self._load_config(filepath=location)
        return self

    def load(self):
        if self.default_options is None:
            self._load_config()

    def _load_config(self, filepath=None):
        if filepath is None:
            if CONFIG_LOCATION is None:
                raise ValueError(NO_CONFIG_LOCATION_ERROR_MESSAGE)
            filepath = os.path.abspath(CONFIG_LOCATION)
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f)
            self.default_options = config

    def __getitem__(self, item):
        if self.default_options is None:
            raise ValueError(CONFIG_NOT_YET_LOADED_ERROR_MESSAGE)
        default = self.default_options.get(item)

        if isinstance(default, dict):
            return Config(_basename=self._create_basename(item),
                          _defaults=default)

        env = self._get_env_var(item)
        if env is None:
            if default is None:
                raise ConfigError(self._create_basename(item),
                                  self._create_env_var_string(item))
            return default
        return env

    def _create_basename(self, item):
        if self.basename:
            return self.basename + '.' + item
        else:
            return item

    def _create_env_var_string(self, item):
        if not self.basename:
            return item.upper()
        else:
            return '_'.join(self._create_basename(item).split('.')).upper()

    def _get_env_var(self, item):
        envvar_string = self._create_env_var_string(item)
        env = os.getenv(envvar_string)
        if env is not None:
            if isinstance(env, str):
                # env vars are always passed in as strings in docker world
                # here we will try to convert them to basic types if we can
                if env.lower() == 'true':
                    return True
                if env.lower() == 'false':
                    return False
                try:
                    env = int(env)
                except ValueError:
                    pass
        return env

