
from waspy import Application, Response, Request
from waspy.transports import RabbitMQTransport, HTTPTransport

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

app = Application((rabbit, http), debug=False)

async def on_startup(app):
    await rabbit.bind_to_exchange(exchange='amq.topic', routing_key='#')


app.on_start.append(on_startup)

# middlewares
async def foo_middleware_factory(app, handler):
    async def middleware(request: Request):
        # Do stuff before handler
        #   dummy example of parsing a header and adding a property
        auth_header = request.headers.get('auth', None)
        request.is_authorized = auth_header is not None

        # handle request
        response = await handler(request)

        # do stuff after handler
        #   dummy example of adding a response header
        response.header['set-auth'] = 'true'


async def handle_hello2(request):
    print(request.__dict__)
    return {'hello': 'world2'}

async def handle_hello(request: Request):
    client = request.app.client
    response = await client.post('', '/hello2', {'some': 'object'})
    print(response)
    return {'hello': 'world'}  # return a dict, it gets parsed to json

async def handle_foo(request: Request):
    fooid = request.path_params.get('fooid')
    return {'foo': fooid}, 202  # you can also return a status code

async def handle_bar(request: Request) -> Response:
    fooid = request.path_params.get('fooid')
    barid = request.query.get('bar')
    return Response(body={'foo': fooid, 'bar': barid})
        # or you can return a response object to include more info
        # such as headers

app.router.add_get('/hello', handle_hello)
app.router.add_post('/hello2', handle_hello2)
app.router.add_get('/foo/:fooid', handle_foo)
app.router.add_get('/foo/:fooid/bar', handle_bar)

if __name__ == '__main__':
    app.run()
