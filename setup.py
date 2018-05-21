from setuptools import setup
from os import path

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='waspy',
    version='0.37.6',
    install_requires=[
        'httptools==0.0.10',
        'aioamqp==0.10.0',
        'pyyaml==3.12',
        'aenum==1.4.5'
    ],
    packages=['waspy', 'waspy.transports'],
    long_description=long_description,
    long_desciption_comtent_type='text/markdown',
    url='https://github.com/wasp/waspy',
    license='Apache 2.0',
    author='nhumrich',
    author_email='nick@humrich.us',
    description='Async Microservices Framework',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords='wasp async asyncio curio rest framework rabbitmq microservices'
)
