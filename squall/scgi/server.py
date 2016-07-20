"""
"""
import logging
from squall.network import SocketStream, SocketServer
from squall.utility import timeout_gen, format_address


logger = logging.getLogger(__name__)


class ScgiServer(SocketServer):

    """ Asynchronous SCGI gateway server.
    """

    def __init__(self, timeout=2.0,
                 chunk_size=8192, buffer_size=262144):
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size
        super(ScgiServer, self).__init__()

    def _stream_factory(self, socket_):
        return SocketStream(socket_, self.chunk_size, self.chunk_size)

    async def _stream_handler(self, stream, address):
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
                await self._request_handler(environ, stream)
            except Exception as exc:
                msg = ("Cannon handle request from %s : %s")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.exception(msg, format_address(address), exc)
                else:
                    logger.error(msg, format_address(address), exc)
        except Exception as exc:
            msg = ("Cannon handle connection from %s : %s")
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(msg, format_address(address), exc)
            else:
                logger.error(msg, format_address(address), exc)
        finally:
            stream.close()

    async def _request_handler(self, environ, stream):
        raise NotImplementedError
