import sys
import logging

from waspy.exceptions import UnsupportedMediaType

logger = logging.getLogger('waspy')


class ErrorLoggingBase:
    def log_exception(self, request, exc_info, level='error'):
        try:
            level = getattr(logging, level.upper())
        except:
            level = logging.ERROR

        logger.log(level, 'An error occurred while handling request: {}'
                   .format(request),
                   exc_info=exc_info)

    def log_warning(self, request, message):
        logger.warning(message)


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

    def _get_sentry_details(self, request, exc_info):
        data = {
            'request': {
                'method': request.method.value,
                'data': request.body if request.original_body else None,
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
        return data, tags, extra_data

    def log_warning(self, request, message=None):
        exc_info = sys.exc_info()
        super().log_warning(request, message=message)
        data, tags, extra = self._get_sentry_details(request, None)
        self.raven.captureException(exc_info=exc_info, message=message,
                                    data=data, extra=extra,
                                    tags=tags, level='warning')

    def log_exception(self, request, exc_info, level='error'):
        super().log_exception(request, exc_info, level=level)

        data, tags, extra = self._get_sentry_details(request, exc_info)
        self.raven.captureException(data=data, extra=extra, tags=tags,
                                    exc_info=exc_info, level=level)

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
