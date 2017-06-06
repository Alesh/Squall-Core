""" Sample "Echo server"
"""
import logging
import sys
from signal import SIGINT

from squall.core.network import TCPServer
from squall.core.utils import Addr, timeout_gen


class EchoServer(TCPServer):
    """ Echo server
    """

    def __init__(self, *, timeout=None):
        self._timeout = timeout or 15.0
        super().__init__(self.echo_handler)

    def unbind(self, port, address=None):
        addr = Addr((address, port))
        super().unbind(port, address)
        logging.info("[%s]Finished echo listener", addr)

    def bind(self, port, address=None, *, backlog=128, reuse_port=False):
        addr = Addr((address, port))
        super().bind(port, address, backlog=backlog, reuse_port=reuse_port)
        logging.info("[%s]Established echo listener", addr)

    async def echo_handler(self, disp, stream, addr):
        addr = Addr(addr)
        logging.info("[%s]Accepted connection", addr)
        try:
            while stream.active:
                timeout = timeout_gen(self._timeout)
                data = await stream.read_until(b'\r\n', timeout=next(timeout))
                if data:
                    await disp.sleep(0.25)  # Lazy response ))
                    stream.write(data)
                else:
                    raise ConnectionResetError("Connection reset by peer")
                await stream.flush()
        except IOError as exc:
            logging.warning("[%s]Connection fail: %s", addr, exc)
        finally:
            logging.info("[%s]Connection has closed", addr)

    def before_start(self, disp):
        async def terminator(disp):
            await disp.signal(SIGINT)
            self.stop()

        disp.submit(terminator)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    server = EchoServer()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    server.bind(port, 'localhost')
    server.start()
