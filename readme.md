# wasp

Wasp is a asynchronous "transport-agnostic" web framework.
It allows you to spin up a RESTful web service that can listen on any transport
such as HTTP, RabbitMQ, or others.

`wasp` stands for a Wicked Async Services Platform.
It is a project designed to make microservices in python easier. 
This repo is the main python web-framework for using wasp.
The org `wickedasp` (wasp was already taken) is for the project as a whole.

## Language agnostic concepts
While this framework is for python, the patterns used in wasp are language
agnostic. You should be able to call other services in different languages
assuming they all follow the same patterns. This framework has a pluggable
architecture for the transport layer, which allows you to switch from
http to using a message bus, or vice-versa. You could even listen on both
at the same time without having to modify your code at all.

## Example
Look at `examples/http_foo.py` for a quick example

## Alpha
This project is currently in alpha state. 
There are a lot of features missing.

Features for beta:
 - [x]: HTTP Transport
 - []: RabbitMQ transport
 - []: Client library (for calling other services)
 - []: HTTP client transport (with envvar service discovery)
 - []: RabbitMQ client transport
 - []: Figure out middleware
 
Wish List:
 - []: Transport classes for nats (nats.io)
 - []: Transport classes for kafka
 - []: pattern for synchronous "worker-tier"
 - []: decorators for adding routes

## License
Apache-2.0

## Installing
To install, you will need to `git clone` for now, and run `pip install .`

## Developing
`python setup.py develop`
