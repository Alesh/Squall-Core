""" Sample "Echo server" based only on base classes
"""
import sys
import errno
import socket
import logging
from signal import SIGINT
from squall.core import Dispatcher
from squall.core.utils import Addr, timeout_gen
from squall.core.network import bind_sockets


async def echo_handler(disp, connection_socket, addr):
    try:
        while True:
            timeout = timeout_gen(15)
            fileno = connection_socket.fileno()
            await disp.ready(fileno, disp.READ, timeout=next(timeout))
            data = connection_socket.recv(1024)
            if data:
                await disp.ready(fileno, disp.WRITE, timeout=next(timeout))
                connection_socket.send(data)
            else:
                raise ConnectionResetError("Connection reset by peer")
    except IOError as exc:
        logging.warning("[{}]Connection fail: {}".format(addr, exc))


async def echo_acceptor(disp, listen_socket):
    connections = dict()
    listen_socket.setblocking(0)
    fileno = listen_socket.fileno()
    addr = Addr(listen_socket.getsockname())
    logging.info("[{}]Established echo listener".format(addr))

    async def serve_connection(disp, connection_socket, address):
        addr = Addr(address)
        key = (connection_socket, address)
        connection_socket.setblocking(0)
        logging.info("[{}]Accepted connection".format(addr))
        try:
            await echo_handler(disp, connection_socket, addr)
        finally:
            connections.pop(key)
            if connection_socket:
                try:
                    connection_socket.shutdown(socket.SHUT_RDWR)
                except IOError:
                    pass
                finally:
                    connection_socket.close()
            logging.info("[{}]Connection has closed".format(addr))

    try:
        while True:
            try:
                await disp.ready(fileno, disp.READ, timeout=1.0)
                while True:
                    try:
                        args = listen_socket.accept()
                        connections[args] = disp.submit(serve_connection, *args)
                    except IOError as exc:
                        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                            break
                        raise exc
            except TimeoutError:
                continue

    except IOError as exc:
        logging.error("[{}]Listenner fail: {}".format(addr, exc))
    finally:
        logging.info("[{}]Finished echo listener".format(addr))
        try:
            listen_socket.shutdown(socket.SHUT_RDWR)
        except IOError:
            pass
        finally:
            listen_socket.close()


async def terminator(disp):
    try:
        await disp.signal(SIGINT)
        print("Got SIGINT!")
    finally:
        disp.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    disp = Dispatcher()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    for socket_ in bind_sockets(port):
        disp.submit(echo_acceptor, socket_)
    disp.submit(terminator)
    disp.start()
