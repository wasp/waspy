import os
import sys
import yaml

FILE_NAME = 'config.yaml'
BASEPATH = os.path.dirname(sys.modules['__main__'].__file__)


class ConfigError(KeyError):
    """ Raised when a requested configuration can not be found """


class ConfigBase:
    def __init__(self):
        self.basename = ''
        self.default_options = {}
        raise TypeError('Should not use ConfigBase directly')

    def __getitem__(self, item):
        """ called when access like a dictionary
                config['database']['username']
        """
        default = self.default_options.get(item)
        if isinstance(default, dict):
            return ConfigSection(self.basename + '.' + item, default)
        # Check for env var
        envvar_string = '_'.join(self.basename.split('.') + [item]).upper()
        env = os.getenv(envvar_string)
        if env is None:
            if default is None:
                raise ConfigError(
                    'No configuration found for "{}". '
                    'Add the environment variable {} or add'
                    ' the key to your config.toml file'.format(
                        '.'.join((self.basename, item)).strip('.'),
                        envvar_string
                    ))
            return default
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


class Config(ConfigBase):
    """ load configuration from envvar or config file
        You can get settings from environment variables or a config.toml file
        Environment variables have a higher precedence over the config file

        Use `config['section']['subsection']['key']` to get the value
        SECTION_SUBSECTION_KEY from environment variables or
        section.subsection.key from a toml file
        (usually written:
            [section.subsection]
            key = value
        in a toml file)
    """
    def __init__(self):
        self.default_options = None
        self.basename = ''

    def load_config(self):
        filepath = os.path.abspath(os.path.join(BASEPATH, FILE_NAME))
        with open(filepath, 'r') as f:
            config = yaml.load(f)
            return config

    def __getitem__(self, item):
        if self.default_options is None:
            self.default_options = self.load_config()
        return super().__getitem__(item)


class ConfigSection(ConfigBase):
    def __init__(self, basename, defaults):
        self.basename = basename.lstrip('.')
        self.default_options = defaults