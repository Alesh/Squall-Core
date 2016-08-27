import logging
from squall import coroutine
from squall.network import TcpBinding, ConnectionAcceptor
from squall.network import format_address, timeout_gen
from squall.stream import SocketStream


class EchoServer(ConnectionAcceptor):

    """ Echo server
    """

    def __init__(self, port, address=None, timeout=None):

        def connection_factory(socket_):
            return SocketStream(socket_)

        self.timeout = timeout or 15
        super(EchoServer, self).__init__(TcpBinding(port, address),
                                         self.connection_handler,
                                         connection_factory)

    def listen(self):
        """ Starts connection listening.
        """
        super(EchoServer, self).listen()
        coroutine.run()

    async def connection_handler(self, stream, address):
        """ Connection handler.
        """
        logging.info("Accepted connection from: {}"
                     "".format(format_address(address)))
        try:
            while True:
                await self.request_handler(stream)
        except IOError as exc:
            logging.warning("Connection from {}: {}"
                            "".format(format_address(address), exc))
        finally:
            stream.close()
            logging.info("Connection from {} has closed"
                         "".format(format_address(address)))

    async def request_handler(self, stream):
        """ Request handler.
        """
        timeout = timeout_gen(self.timeout)
        data = await stream.read_until(b'\n', timeout=next(timeout))
        await stream.write(data, timeout=next(timeout), flush=True)


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    echo_server = EchoServer(22077)
    echo_server.listen()
