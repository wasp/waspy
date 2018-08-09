from http import HTTPStatus


class ResponseError(Exception):
    def __init__(self, message=None, status: HTTPStatus=None, *, body=None, headers=None,
                 correlation_id=None, reason=None, content_type=None, log=False):
        super().__init__(message)
        self.message = message
        if hasattr(self, 'status') and status is None:
            status = self.status
        if hasattr(self, 'body') and body is None:
            body = self.body
        if hasattr(self, 'reason') and reason is None:
            reason = self.reason
        if hasattr(self, 'log') and log is False:
            log = self.log
        if hasattr(self, 'content_type') and content_type is None:
            content_type = self.content_type
        if reason and not body:
            body = {'reason': reason}

        self.status = status
        self.body = body
        self.log = log
        self.headers = headers
        self.correlation_id = correlation_id
        self.reason = reason
        self.content_type = content_type


class ParseError(ResponseError):
    status = HTTPStatus.BAD_REQUEST

    def __init__(self, reason):
        """
        Example
            raise ParseError("Invalid JSON")
        """
        super().__init__(message=reason, reason=reason)


class UnsupportedMediaType(ResponseError):
    status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    def __init__(self, content_type):
        super().__init__(
            message=content_type,
            reason=f'Unsupported media type "{content_type}" in request'
        )


class NotRoutableError(ResponseError):
    status = HTTPStatus.NOT_FOUND
    reason = 'No route found'
