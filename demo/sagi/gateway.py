""" Application gateways
"""
import sys
import logging
import traceback
from http.server import BaseHTTPRequestHandler

from squall.network import SocketAcceptor, SocketStream
from squall.utility import timeout_gen, format_address

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

    """ SAGI Gateway
    """

    def __init__(self, app, *, timeout=None, stream_factory=None):
        self.app = app
        self.timeout = timeout
        self.acceptors = list()
        self.stream_factory = (stream_factory or
                               (lambda sock: SocketStream(sock, 8192, 262144)))

    def active(self):
        """ Returns `True` if gateway is active"""
        return len(self.acceptors) > 0

    def start(self, sockets):
        """ Starts
        """
        def stream_factory(socket_):
            return SocketStream(socket_, 8192, 262144)

        acceptor = SocketAcceptor(sockets, self.connection_handler,
                                  self.stream_factory or stream_factory)
        if acceptor.listen():
            self.acceptors.append(acceptor)

    def stop(self):
        for acceptor in self.acceptors:
            acceptor.close()
        self.acceptors.clear()

    async def connection_handler(self, stream, address):
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
                await self.request_handler(environ, stream)
            except Exception as exc:
                msg = ("{}: Cannon handle request from %s : %s"
                       "".format(self.__class__.__name__))
                if logger.isEnabledFor(logging.DEBUG):
                    logger.exception(msg, format_address(address), exc)
                else:
                    logger.error(msg, format_address(address), exc)
        except Exception as exc:
            msg = ("{}: Cannon handle connection from %s"
                   "".format(self.__class__.__name__))
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(msg, format_address(address), exc)
            else:
                logger.error(msg, format_address(address), exc)
        finally:
            stream.close()

    async def request_handler(self, environ, stream):
        """ Async SCGI request handler
        """
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
