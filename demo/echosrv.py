""" The example of async TCP echo server.
"""
import logging
from squall.network import SocketServer
from squall.utility import timeout_gen


class EchoServer(SocketServer):

    def __init__(self):
        super(EchoServer, self).__init__()
        self._stream_handler = self.handle_stream

    async def handle_stream(self, stream, address):
        logging.info("Accepted connection: {}".format(address))
        try:
            while True:
                tg = timeout_gen(15)
                data = await stream.read_until(b'\n', timeout=next(tg))
                await stream.write(data, timeout=next(tg), flush=True)
        except IOError as exc:
            logging.warning("Connection from {}: {}".format(address, exc))
        finally:
            logging.info("Connection from {} closed.".format(address))


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)

    echo_server = EchoServer()
    echo_server.bind(22077, '127.0.0.1')
    echo_server.start()
