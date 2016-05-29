""" Async echo server based on low level functions.
"""
import errno
import logging
from socket import SHUT_RDWR

from squall import coroutine
from squall.coroutine import ready, READ, WRITE
from squall.network import bind_sockets, timeout_gen


async def echo_handler(socket, address):
    fd = socket.fileno()
    logging.info("Accepted connection: {}".format(address))
    try:
        while True:
            tg = timeout_gen(15)
            await ready(fd, READ, timeout=next(tg))
            data = socket.recv(1024)
            if data:
                await ready(fd, WRITE, timeout=next(tg))
                socket.send(data)
            else:
                raise ConnectionResetError(errno.ECONNRESET,
                                           "Connection reset by peer")
    except IOError as exc:
        logging.warning("Connection from {}: {}".format(address, exc))
    finally:
        logging.info("Connection from {} closed.".format(address))


async def echo_acceptor(socket):
    connections = dict()
    logging.info("Established echo listener on {}"
                 "".format(socket.getsockname()))

    async def _serve(connection):
        client_socket, address = connection
        try:
            await echo_handler(client_socket, address)
        finally:
            connections.pop(connection)
            if client_socket:
                try:
                    client_socket.shutdown(SHUT_RDWR)
                finally:
                    client_socket.close()

    try:
        fd = socket.fileno()
        while True:
            await ready(fd, READ)
            while True:
                try:
                    conn = socket.accept()
                    connections[conn] = coroutine.spawn(_serve, conn)
                except IOError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        break
                    raise exc

    finally:
        logging.info("Finished echo listener on {}"
                     "".format(socket.getsockname()))
        socket.shutdown(SHUT_RDWR)
        socket.close()


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    for socket in bind_sockets(22077, backlog=128):
        coroutine.spawn(echo_acceptor, socket)
    coroutine.run()
