from distutils.core import setup

setup(
    name='wasp',
    version='0.0.0',
    requires=[
        'h11',

    ],
    packages=['wasp', 'wasp.transports', 'tests'],
    url='https://github.com/wickedasp/wasp',
    license='Apache 2.0',
    author='nhumrich',
    author_email='',
    description='Async microservices framework'
)
