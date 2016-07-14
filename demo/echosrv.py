""" The example of single-threaded async TCP server.
"""
import logging
from squall import coroutine
from squall.network import SocketAcceptor
from squall.utility import bind_sockets, timeout_gen


class EchoServer(SocketAcceptor):

    def __init__(self, port):
        sockets = bind_sockets(port)
        super(EchoServer, self).__init__(sockets, self.handle_connection)

    def listen(self):
        super(EchoServer, self).listen()
        coroutine.run()

    async def handle_connection(self, stream, address):
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
    echo_server = EchoServer(22077)
    echo_server.listen()
