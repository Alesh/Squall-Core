""" Application gateways
"""
import sys
import traceback
from http.server import BaseHTTPRequestHandler


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

    """ Squall asynchronous gateway interface.
    """

    def __init__(self, app, *,
                 timeout=None, chunk_size=8192, buffer_size=262144):
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
