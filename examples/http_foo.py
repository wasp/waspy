
from waspy import Application
from waspy.transports import HTTPTransport

app = Application(HTTPTransport(port=8080, prefix='/api'), debug=False)


async def handle_hello(request):
    return {'hello': 'world'}, 502

async def handle_foo(request):
    fooid = request.path_params.get('fooid')
    return {'foo': fooid}

async def handle_bar(request):
    fooid = request.path_params.get('fooid')
    barid = request.query.get('bar')
    return {'foo': fooid, 'bar': barid}

async def handle_options(request):
    return {'hello': 'world'}

app.router.add_static_route('get', '/hello', handle_hello)
app.router.add_get('/foo/:fooid', handle_foo)
app.router.add_get('/foo/:fooid/bar', handle_bar)
app.router.add_generic_options_handler(handle_options)

if __name__ == '__main__':
    app.run()
