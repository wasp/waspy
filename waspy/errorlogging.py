
import logging

logger = logging.getLogger('waspy')


class ErrorLoggingBase:
    def log_exception(self, request, exc_info):
        logger.error('An error occurred while handling request: {}'
                     .format(request),
                     exc_info=exc_info)


class SentryLogging(ErrorLoggingBase):
    def __init__(self, *, dsn, environment):
        try:
            from raven import Client
        except ImportError as e:
            raise ImportWarning(
                'You must install raven in order to use the sentry logger'
            ) from e

        self.raven = Client(dsn, environment=environment)
        self.raven.transaction.clear()

    def log_exception(self, request, exc_info):
        super().log_exception(request, exc_info)

        data = {
            'request': {
                'method': request.method.value,
                'data': request.body,
                'query_string': request.query_string,
                'url': '/' + request.path.replace('.', '/'),
                'content-type': request.content_type,
                'headers': request.headers
            },
            'user': {
            }
        }
        tags = {  # put things you want to filter by in sentry here
            'handler': request._handler.__qualname__,
        }
        extra_data = {  # put extra data here
            'correlation_id': request.correlation_id
        }

        self.add_context_data(request, data, tags, extra_data, exc_info)
        self.raven.captureException(data=data, extra=extra_data, tags=tags,
                                    exc_info=exc_info, duration=20)

    def add_context_data(self, request, data, tags, extra_data, exc_info):
        """
        Override this method to add your own sentry data.
        :param request: the request the error occured on
        :param data: This is the normal sentry data, prepopulated with the
        request data for you. Dictionary.
        :param tags: things you want to filter by in sentry. Dictionary
        :param extra_data: extra informational data. Dictionary
        :param exc_info: the exception info tuple provide from sys.exc_info()
        :return: Nothing. Just modify the passed in dictionaries
        """
        pass
