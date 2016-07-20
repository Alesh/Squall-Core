"""
"""
import logging
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


def Status(code):
    """ Makes HTTP status string.
    """
    status = BaseHTTPRequestHandler.responses.get(code, ("ERROR", ""))[0]
    return "{} {}".format(code, status)


class HTTPError(Exception):

    """ HTTP Error
    """

    def __init__(self, code, headers=[]):
        self.status = Status(code)
        self.headers = headers
        super(HTTPError, self).__init__(self.status)


class ErrorStream(object):

    """ Error stream
    """

    def __init__(self, environ):
        self.extra = {'ip': environ.get('REMOTE_ADDR', 'UNKNOWN')}

    def write(self, line):
        """ Writes one line error message.
        """
        logger.error(line, extra=self.extra)

    def writelines(self, lines):
        """ Writes multi line error message.
        """
        for line in lines:
            self.write(line)

    def flush():
        """ Flushes log.
        """
        for handler in logger.handlers:
            handler.flush()


class InputStream(object):

    """ Input stream
    """

    def __init__(self, environ, stream):
        self._stream = stream

    async def read_bytes(self, number, *, timeout=None):
        """ Asynchronously reads a number of bytes.
        """
        return await self._stream.read_bytes(number, timeout=timeout)

    async def read_until(self, delimiter, *, timeout=None, max_bytes=None):
        """ Asynchronously reads until we have found the given delimiter.
        """
        return await self._stream.read_until(delimiter,
                                             timeout=timeout,
                                             max_bytes=max_bytes)


class StartResponse(object):

    """ Start response.
    """

    def __init__(self, stream, protocol, encode=None):
        self.encode = encode or 'ISO-8859-1'
        self.headers_sent = False
        self.protocol = protocol
        self.headers = list()
        self.stream = stream

    def __call__(self, status, response_headers, exc_info=None):
        if exc_info:
            try:
                if self.headers_sent:  # headers already sent
                    raise exc_info[1].with_traceback(exc_info[2])
            finally:
                exc_info = None
        elif self.headers:
            raise AssertionError("Headers already set!")
        self.headers.append("{} {}".format(self.protocol, status))
        for name, value in response_headers:
            self.headers.append("{}: {}".format(name, value))
        return self.write

    async def write(self, data=None, *, timeout=None, flush=False):
        if not self.headers:
            raise AssertionError("write() before start_response()")
        elif not self.headers_sent:
            headers = ''
            for header in self.headers:
                headers += header + '\r\n'
            headers += '\r\n'
            await self.stream.write(headers.encode(self.encode))
            self.headers_sent = True
        await self.stream.write(data, timeout=timeout, flush=flush)
