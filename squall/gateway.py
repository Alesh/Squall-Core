""" Application gateways
"""
import sys
import logging
import traceback
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


def Status(code):
    """ Makes HTTP status string.
    """
    status = BaseHTTPRequestHandler.responses.get(code, ("ERROR", ""))[0]
    return "{} {}".format(code, status)


class ErrorStream(object):

    """ Request error stream
    """
    def __init__(self, environ, obj):
        self.source = obj.__class__.__name__
        self.extra = {'ip': environ.get('REMOTE_ADDR', 'UNKNOWN')}

    def write(self, line):
        """ Writes one line error message.
        """
        logging.error('%s: %s', self.source, line, extra=self.extra)

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

    """ Controller of start response.
    """

    def __init__(self, stream, protocol):
        self.protocol = protocol
        self.headers_sent = False
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
            await self.stream.write(headers.encode('ISO-8859-1'))
            self.headers_sent = True
        await self.stream.write(data, timeout=timeout, flush=flush)


class SAGIGateway(object):

    """ Squall Asynchronous Gateway Interface.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, environ, stream):
        environ.pop('SCGI', None)
        environ.pop('DOCUMENT_URI', None)
        environ.pop('QUERY_STRING', None)
        environ['sagi.version'] = (1, 0)
        environ['sagi.errors'] = ErrorStream(environ, self)
        environ['sagi.input'] = InputStream(environ, stream)
        request_uri = environ.pop('REQUEST_URI', '')
        script_name = environ.pop('SCRIPT_NAME', '')
        scheme = environ.pop('REQUEST_SCHEME', 'http')
        query_pos = request_uri.find('?')
        if query_pos > 0:
            path_info = request_uri[:query_pos]
            environ['QUERY_STRING'] = request_uri[query_pos+1:]
        else:
            path_info = request_uri
        if path_info.find(script_name):
            path_info = path_info[len(script_name):]
        environ['SCRIPT_NAME'] = script_name
        environ['PATH_INFO'] = path_info
        if environ.pop('HTTPS', 'off') in ('on', '1'):
            environ['sagi.url_scheme'] = 'https'
        else:
            environ['sagi.url_scheme'] = scheme
        # Makes an environ compatible with WSGI tools.
        environ['wsgi.version'] = (1, 0)
        environ['wsgi.errors'] = environ['sagi.errors']
        environ['wsgi.url_scheme'] = environ['sagi.url_scheme']
        try:
            start_response = StartResponse(stream, environ['SERVER_PROTOCOL'])
            await self.app(environ, start_response)
        except:
            exc_info = sys.exc_info()
            if isinstance(exc_info[1], TimeoutError):
                status = Status(408)
            else:
                status = Status(500)
            write = start_response(status, [
                ('Content-type', 'text/plain; charset=utf-8')], exc_info)
            for line in traceback.format_exception(*exc_info):
                await write(line.encode('UTF-8'))
        finally:
            await start_response.write(flush=True)
