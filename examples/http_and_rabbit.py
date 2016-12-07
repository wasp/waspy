
from wasp import Application
from wasp.transports import RabbitMQTransport, HTTPTransport

rabbit = RabbitMQTransport(
    url='127.0.0.1',  # requires rabbitmq running locally (docker?)
    port=5672,
    queue='myqueue',
    virtualhost='/',
    username='guest',
    password='guest',
    ssl=False
)
http = HTTPTransport(port=8080)

app = Application((http, rabbit), debug=False)

async def on_startup(app):
    await rabbit.bind_to_exchange(exchange='amq.topic', routing_key='#')


app.on_start.append(on_startup)


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
