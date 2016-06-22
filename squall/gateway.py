""" Application gateways
"""
import sys
import logging
import traceback
from http.server import BaseHTTPRequestHandler

from squall.network import SocketStream, SocketAcceptor, timeout_gen

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

    """ Request error stream
    """
    def __init__(self, environ, obj):
        self.source = obj.__class__.__name__
        self.extra = {'ip': environ.get('REMOTE_ADDR', 'UNKNOWN')}

    def write(self, line):
        """ Writes one line error message.
        """
        logger.error('%s: %s', self.source, line, extra=self.extra)

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
        environ.pop('DOCUMENT_ROOT', None)
        protocol = environ.pop('SERVER_PROTOCOL', None)
        environ['SERVER_PROTOCOL'] = protocol or 'HTTP/1.0'
        request_uri = environ.pop('REQUEST_URI', '')
        script_name = environ.pop('SCRIPT_NAME', '/')
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
        environ['PATH_INFO'] = path_info or '/'
        # Squall specific envirin variable.
        environ['squall.version'] = (1, 0)
        environ['squall.errors'] = ErrorStream(environ, self)
        environ['squall.input'] = InputStream(environ, stream)
        if environ.pop('HTTPS', 'off') in ('on', '1'):
            environ['squall.url_scheme'] = 'https'
        else:
            environ['squall.url_scheme'] = scheme
        try:
            start_response = StartResponse(stream, environ['SERVER_PROTOCOL'])
            await self.app(environ, start_response)
        except:
            headers = [('Content-type', 'text/plain; charset=utf-8')]
            exc_info = sys.exc_info()
            if isinstance(exc_info[1], HTTPError):
                status = Status(exc_info[1].status)
                headers.extend(exc_info[1].headers)
            elif isinstance(exc_info[1], TimeoutError):
                status = Status(408)
            else:
                status = Status(500)
            write = start_response(status, headers, exc_info)
            for line in traceback.format_exception(*exc_info):
                await write(line.encode('UTF-8'))
        finally:
            await start_response.write(flush=True)


class SCGIBackend(SocketAcceptor):

    """ SCGI Backend
    """

    def __init__(self, gateway, sockets, *,
                 timeout=None, chunk_size=8192, buffer_size=262144):
        def stream_factory(socket_):
            return SocketStream(socket_, chunk_size, buffer_size)
        super(SCGIBackend, self).__init__(sockets, stream_factory)
        self.timeout = timeout
        self.gateway = gateway

    async def handle_connection(self, stream, address):
        """ Connection handler
        """
        try:
            timeout = timeout_gen(self.timeout)
            data = await stream.read_until(b':',
                                           timeout=next(timeout),
                                           max_bytes=16)
            if data[-1] != ord(b':'):
                raise ValueError("Wrong header size")
            data = await stream.read_bytes(int(data[:-1]) + 1,
                                           timeout=next(timeout))
            if data[-1] != ord(b','):
                raise ValueError("Wrong header format")
            items = data.decode('UTF8').split('\000')
            environ = dict(zip(items[::2], items[1::2]))
            try:
                await self.gateway(environ, stream)
            except:
                logger.exception("%s: Cannon handle request:",
                                 self.__class__.__name__,
                                 extra={'ip': address})
        except Exception as exc:
            logger.warning("%s: Cannon handle connection: %s",
                           self.__class__.__name__, str(exc),
                           extra={'ip': address})
        finally:
            stream.close()
