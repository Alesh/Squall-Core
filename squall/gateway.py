""" Application gateways
"""
import io
import sys
import logging
import traceback
from http.server import BaseHTTPRequestHandler

from squall.network import timeout_gen


def Status(code):
    """ Makes HTTP status string.
    """
    status = BaseHTTPRequestHandler.responses.get(code, ("ERROR", ""))[0]
    return "{} {}".format(code, status)


class StartResponse(object):

    """ Start response
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
        temp = environ.pop('SCGI', '1') + ".0"
        environ['scgi.version'] = tuple(map(int, temp.split(".")[:2]))
        environ['async.read_bytes'] = stream.read_bytes
        environ['async.read_until'] = stream.read_until
        start_response = StartResponse(stream, environ['SERVER_PROTOCOL'])
        try:
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


class ErrorStream(object):

    """ Request error stream
    """

    def write(self, line):
        logging.error(line)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush():
        pass


class WSGIGateway(object):

    """ Web Server Gateway Interface.
    """

    def __init__(self, app, *, timeout=None):
        self.app = app
        self.timeout = timeout
        self.default = {
            'wsgi.version': (1, 0),
            'wsgi.errors': ErrorStream(),
            'wsgi.multithread': False,
            'wsgi.multiprocess': True,
            'wsgi.run_once': False
        }

    async def __call__(self, environ, stream):
        environ.pop('SCGI', None)
        environ.pop('SCRIPT_NAME', None)
        environ.pop('DOCUMENT_URI', None)
        environ.pop('DOCUMENT_ROOT', None)
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
            environ['wsgi.url_scheme'] = 'https'
        else:
            environ['wsgi.url_scheme'] = scheme
        try:
            input_body = b''
            input_size = environ['CONTENT_LENGTH']
            input_size = int(input_size) if input_size else 0
            timeout = timeout_gen(self.timeout)
            while input_size > 0:
                data = await stream.read_bytes(stream.chunk_size,
                                               timeout=next(timeout))
                input_size -= len(input_size)
                input_body += data
            environ['wsgi.input'] = io.BytesIO(input_body)
            start_response = StartResponse(stream, environ['SERVER_PROTOCOL'])
            for chunk in self.app(environ, start_response):
                await start_response.write(chunk)
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
