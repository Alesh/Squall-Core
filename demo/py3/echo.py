import os
import sys
import logging
from squall.network import TCPServer

logger = logging.getLogger('echo.py')


class EchoServer(TCPServer):
    """ Sample echo server.
    """

    def __init__(self):
        def on_listen(addr):
            logger.info("Established echo listener "
                        "on {} pid: {}".format(addr, os.getpid()))

        def on_finish(addr):
            logger.info("Finished echo listener "
                        "on {} pid: {}".format(addr, os.getpid()))

        super().__init__(on_listen=on_listen, on_finish=on_finish)

    async def request_handler(self, stream, addr):
        """ Request handler
        """
        logger.info("Accepted connection from {} pid: {}"
                    "".format(addr, os.getpid()))
        try:
            while not stream.closed:
                data = await stream.read_until(b'\r\n', timeout=15)
                stream.write(data)
        except IOError as exc:
            logger.warning("Connection from {} fail: {}".format(addr, exc))
        finally:
            if not stream.closed:
                stream.abort()
            logger.info("Connection from {} has closed".format(addr))

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    EchoServer().start(port, workers=0)
