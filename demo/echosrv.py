""" Sample "Echo server"
"""
import logging
import sys
from signal import SIGINT

from squall.core.networking import TCPServer, Addr
from squall.core.switching import timeout_gen


class EchoServer(TCPServer):
    """ Echo server
    """

    def __init__(self, *, timeout=None):
        self._timeout = timeout or 15.0
        super().__init__(self.echo_handler)

    def unbind(self, port, address=None):
        addr = Addr((address, port))
        super().unbind(port, address)
        logging.info("[{}]Finished echo listener".format(addr))

    def bind(self, port, address=None, *, backlog=128, reuse_port=False):
        addr = Addr((address, port))
        super().bind(port, address, backlog=backlog, reuse_port=reuse_port)
        logging.info("[{}]Established echo listener".format(addr))

    async def echo_handler(self, api, stream, addr):
        logging.info("[{}]Accepted connection".format(addr))
        try:
            while stream.active:
                timeout = timeout_gen(self._timeout)
                data = await stream.read_until(b'\r\n\r\n', timeout=next(timeout))
                if data:
                    # await api.sleep(0.25)  # Lazy response ))
                    stream.write(data)
                else:
                    raise ConnectionResetError("Connection reset by peer")
                await stream.flush()
                break
        except IOError as exc:
            logging.warning("[{}]Connection fail: {}".format(addr, exc))
        finally:
            logging.info("[{}]Connection has closed".format(addr))

    def before_start(self, api):
        async def terminator(api):
            await api.signal(SIGINT)
            self.stop()

        api.submit(terminator)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)

    server = EchoServer()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    server.bind(port, 'localhost')
    server.start()
