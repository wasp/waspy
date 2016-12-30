
from waspy import Application
from waspy.transports import HTTPTransport

app = Application(HTTPTransport(port=8080), debug=False)


async def handle_hello(request):
    return {'hello': 'world'}

async def handle_foo(request):
    fooid = request.path_params.get('fooid')
    return {'foo': fooid}

async def handle_bar(request):
    fooid = request.path_params.get('fooid')
    barid = request.query.get('bar')
    return {'foo': fooid, 'bar': barid}

app.router.add_static_route('get', '/hello', handle_hello)
app.router.add_get('/foo/:fooid', handle_foo)
app.router.add_get('/foo/:fooid/bar', handle_bar)

if __name__ == '__main__':
    app.run()
