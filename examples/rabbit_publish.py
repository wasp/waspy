import pika

connection = pika.BlockingConnection(pika.ConnectionParameters(
    'localhost'
))
channel = connection.channel()
channel.queue_declare(queue='reply_queue', durable=True, auto_delete=False)
properties = pika.BasicProperties(
    type='get', correlation_id='aabbccdd', headers={'query': '?bar=12df3'},
    delivery_mode=1,
    reply_to='reply_queue'
)
channel.basic_publish(exchange='amq.topic', routing_key='hello',
                      body='None', properties=properties, mandatory=True)

channel.basic_publish(exchange='amq.topic', routing_key='foo.123',
                      body='None', properties=properties, mandatory=True)

delivered = channel.basic_publish(exchange='amq.topic', routing_key='foo.123.bar',
                                  body='None', properties=properties,
                                  mandatory=True)

print(delivered)

