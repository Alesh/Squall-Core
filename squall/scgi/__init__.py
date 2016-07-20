"""
"""
import sys
import traceback

from .server import ScgiServer
from .app import ErrorStream, InputStream
from .app import StartResponse, Status, HTTPError


class Server(ScgiServer):

    """ Asynchronous SCGI application server.
    """

    def __init__(self, app, *, timeout=2.0,
                 chunk_size=8192, buffer_size=262144):
        self.app = app
        super(Server, self).__init__(timeout, chunk_size, buffer_size)

    def _update_environ(self, environ, stream):
        environ['squall.errors'] = ErrorStream(environ)
        environ['squall.input'] = InputStream(environ, stream)

    async def _request_handler(self, environ, stream):
        self._update_environ(environ, stream)
        protocol = environ.setdefault('SERVER_PROTOCOL', 'HTTP/1.0')
        try:
            start_response = StartResponse(stream, protocol)
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
