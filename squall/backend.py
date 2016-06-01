""" Application backends.
"""
import logging

from squall.network import SocketStream, SocketAcceptor, timeout_gen


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
                logging.exception("Cannon handle request")
        except Exception as exc:
            logging.info("Cannon handle connection {}: {}"
                         "".format(address, exc))
        finally:
            stream.close()
