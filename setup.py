from setuptools import setup

setup(
    name='waspy',
    version='0.0.0',
    install_requires=[
        'h11==0.7.0',
        'aioamqp==0.8.2'
    ],
    packages=['waspy'],
    url='https://github.com/wasp/waspy',
    license='Apache 2.0',
    author='nhumrich',
    author_email='',
    description='Async Microservices Framework'
)
