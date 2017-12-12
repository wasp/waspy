# WASPy

Waspy is the python framework for the [WASP project](https://github.com/wasp/wasp). 
    In other words its an asynchronous "transport-agnostic" web framework.

## Language agnostic concepts
While this framework is for python, the patterns used in wasp are language
agnostic. You should be able to call other services in different languages
assuming they all follow the same patterns. This framework has a pluggable
architecture for the transport layer, which allows you to switch from
http to using a message bus, or vice-versa. You could even listen on both
at the same time without having to modify your code at all.

## Example
Look at `examples/` folder for some quick examples, or there is an entire example repo at https://github.com/wasp/waspy-example

## Alpha
This project is currently in alpha state. 
There are a lot of features missing.

Features for beta:
- [x] HTTP Transport
- [x] Routing
- [x] RabbitMQ transporty
- [x] Support middlewares
- [x] Client library (for calling other services)
- [x] HTTP client transport (with envvar service discovery)
- [x] RabbitMQ client transport
- [ ] Test everything

note: all alpha features are complete, but I am still in the process of adding more robusts tests. Until that is done, waspy will remain in alpha and api's might change.
 
Wish List:
- [ ] Transport classes for nats (nats.io)
- [ ] Transport classes for kafka
- [ ] pattern for synchronous "worker-tier"
- [x] configuration package
- [ ] auto-reloading when in debug mode
- [x] sentry integration
- [ ] jwt handling

Features for GA (1.0):
- [ ] High level "Falcon-like" api for writing RESTFUL endpoints even easier!
- [ ] High level can be overridden by lower level for control/performance reasons
- [ ] Stable/proven API

## License
Apache-2.0

## Installing
To install, just run `pip install waspy`

## Developing
`python setup.py develop`
