#!/bin/env python3
import os

os.environ['WASPY_CONFIG_LOCATION'] = os.path.join(os.path.dirname(__file__),
                                                   'config.yaml')
from waspy import Application
from waspy.transports import HTTPTransport
from waspy import config

PORT = config['http']['port']

app = Application(HTTPTransport(port=PORT, prefix='/api'), debug=False)


async def handle_hello(request):
    return {'hello': 'world'}

async def handle_foo(request):
    fooid = request.path_params.get('fooid')
    return {'foo': fooid}

async def handle_foo_bar(request):
    foobarid = request.path_params.get('foobarid')
    return {'foo': {'bar': {'id': foobarid}}}

async def handle_bar(request):
    fooid = request.path_params.get('fooid')
    barid = request.query.get('bar')
    return {'foo': fooid, 'bar': barid}

async def handle_options(request):
    return None, 204

app.router.add_static_route('get', '/hello', handle_hello)
app.router.add_get('/hello/world/i/am/bob', handle_hello)
app.router.add_get('/foo/:fooid', handle_foo)
app.router.add_get('/foo/:fooid/bar', handle_bar)
app.router.add_generic_options_handler(handle_options)
app.router.add_get('/foo/bar/:foobarid', handle_foo_bar)

if __name__ == '__main__':
    app.run()
