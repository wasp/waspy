import os
import yaml

CONFIG_LOCATION = os.getenv('WASPY_CONFIG_LOCATION')


class ConfigError(KeyError):
    """ Raised when a requested configuration can not be found """


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

    def _load_config(self):
        if CONFIG_LOCATION is None:
            raise ValueError('Environment variable "{}" is not set. '
                             'You must set it before using the config module, '
                             'ideally in `yourmodule.__init__` file or at '
                             'the system level'.format('WASPY_CONFIG_LOCATION')
                             )
        filepath = os.path.abspath(CONFIG_LOCATION)
        with open(filepath, 'r') as f:
            config = yaml.load(f)
            return config

    def __getitem__(self, item):
        if self.default_options is None:
            self.default_options = self._load_config()
        default = self.default_options.get(item)

        if isinstance(default, dict):
            return Config(_basename=self._create_basename(item),
                          _defaults=default)

        env = self._get_env_var(item)
        if env is None:
            if default is None:
                raise ConfigError(
                    'No configuration found for "{}". '
                    'Add the environment variable {} or add'
                    ' the key to your config.toml file'.format(
                        self._create_basename(item),
                        self._create_env_var_string(item)
                    ))
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
            # env vars are always passed in as strings in docker world
            # here we will try to convert them to basic types if we can
            if env.lower() == 'true':
                env = True
            if env.lower() == 'false':
                env = False
            try:
                env = int(env)
            except ValueError:
                pass
        return env

