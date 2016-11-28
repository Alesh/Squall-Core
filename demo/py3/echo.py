import os
import sys
import logging
from squall.network import TCPServer
from squall.utils import pretty_addr

logger = logging.getLogger('echo.py')


class EchoServer(TCPServer):
    """ Sample echo server.
    """

    def __init__(self):
        super(EchoServer, self).__init__(256, 0)
        self.on_listen = lambda addr: logger.info(
            "Established echo listener on {} pid: {}"
            "".format(pretty_addr(addr), os.getpid()))
        self.on_finish = lambda addr: logger.info(
            "Finished echo listener on {} pid: {}"
            "".format(pretty_addr(addr), os.getpid()))

    async def handle_stream(self, stream, addr):
        """ Request handler
        """
        logger.info("Accepted connection from {} pid: {}"
                    "".format(pretty_addr(addr), os.getpid()))
        try:
            while not stream.closed:
                data = await stream.read_until(b'\r\n', timeout=15)
                stream.write(data)
        except IOError as exc:
            logger.warning("Connection from {} fail: {}"
                           "".format(pretty_addr(addr), exc))
        finally:
            if not stream.closed:
                stream.abort()
            logger.info("Connection from {} has closed".format(addr))

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    EchoServer().start(port, worker=0)
