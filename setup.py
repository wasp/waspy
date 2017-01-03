from setuptools import setup

try:
    import pypandoc
    long_description = pypandoc.convert('readme.md', 'rst')
except(IOError, ImportError):
    long_description = open('readme.md').read()

setup(
    name='waspy',
    version='0.2.3',
    install_requires=[
        'h11==0.7.0',
        'aioamqp==0.8.2'
    ],
    packages=['waspy', 'waspy.transports'],
    long_description=long_description,
    url='https://github.com/wasp/waspy',
    license='Apache 2.0',
    author='nhumrich',
    author_email='nick at humrich dot us',
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
    keywords='wasp async asyncio curio rest framework rabbitmq'
)


