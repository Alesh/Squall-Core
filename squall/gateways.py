""" Application gateways
"""
import sys
import logging
import traceback
from http.server import BaseHTTPRequestHandler

from squall.network import SocketStream, SocketAcceptor, timeout_gen


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


class SCGIGateway(object):

    """ SCGI Gateway
    """

    def __init__(self, app, *,
                 timeout=None, chunk_size=8192, buffer_size=262144):
        self.app = app
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size

    async def handle_request(self, environ, stream):
        temp = environ.pop('SCGI', '1')
        environ['scgi.version'] = tuple(map(int, temp.split(".")[:2]))
        environ['scgi.read_bytes'] = stream.read_bytes
        environ['scgi.read_until'] = stream.read_until
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


class SCGIAcceptor(SocketAcceptor):

    """ SCGI Backend
    """

    def __init__(self, gateway, sockets):
        def stream_factory(socket_):
            return SocketStream(socket_,
                                gateway.chunk_size,
                                gateway.buffer_size)
        super(SCGIAcceptor, self).__init__(sockets, stream_factory)
        self.timeout = gateway.timeout
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
                await self.gateway.handle_request(environ, stream)
            except:
                logging.error("Cannon handle request")
        except Exception as exc:
            logging.info("Cannon handle connection {}: {}"
                         "".format(address, exc))
        finally:
            stream.close()
