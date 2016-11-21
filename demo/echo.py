import sys
import logging
from squall import coroutine
from squall.network import bind_sockets, SocketAcceptor, SocketStream

logger = logging.getLogger('echo.py')


class EchoServer(object):
    """ Sample echo server.
    """
    def __init__(self, port, addr=None, backlog=64):

        def connection_factory(sock, addr):
            return (SocketStream(sock, 256), addr)

        self._acceptors = dict()
        for sock in bind_sockets(port, addr, backlog=backlog):
            acceptor = SocketAcceptor(sock, self.handler,
                                      connection_factory)
            acceptor.on_listen = \
                lambda addr: logger.info("{} Established echo listener"
                                         "".format(addr))
            acceptor.on_finish = \
                lambda addr: logger.info("{} Finished echo listener"
                                         "".format(addr))
            self._acceptors[sock] = acceptor

    def listen(self):
        """ Starts echo server
        """
        for acceptor in self._acceptors.values():
            acceptor.listen()
        coroutine.start()

    async def handler(self, stream, address):
        """ Connection handler
        """
        logger.info("{} Accepted connection".format(address))
        try:
            while not stream.closed:
                data = await stream.read_until(b'\r\n', timeout=15)
                stream.write(data)
        except IOError as exc:
            logger.warning("{} Connection fail: {}".format(address, exc))
        finally:
            stream.close()
            logger.info("{} Connection has closed".format(address))


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    EchoServer(port).listen()
