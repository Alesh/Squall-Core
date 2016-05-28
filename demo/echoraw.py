""" Async echo server based on low level functions.
"""
import logging
from socket import SHUT_RDWR

from squall.coroutine import run, spawn
from squall.coroutine import ready, READ, WRITE
from squall.network import bind_sockets, timeout_gen


async def echo_handler(socket, address, timeout):
    fd = socket.fileno()
    while True:
        tg = timeout_gen(timeout)
        await ready(fd, READ, timeout=next(tg))
        data = socket.recv(1024)
        if data:
            await ready(fd, WRITE, timeout=next(tg))
            socket.send(data)
        else:
            raise ConnectionResetError("reset by peer")


async def echo_acceptor(socket):
    connections = dict()
    logging.info("Established echo listener on {}"
                 "".format(socket.getsockname()))

    async def connection_handler(client_socket, address):
        close_reason = None
        try:
            logging.info("Accepted connection: {}".format(address))
            await echo_handler(client_socket, address, 15)
        except TimeoutError:
            close_reason = "reset by timeout"
        except IOError as exc:
            close_reason = str(exc)
        finally:
            close_reason = close_reason or "reset by host"
            logging.warning("Closing connection: {}"
                            " {}".format(address, close_reason))
            connections.pop(client_socket.fileno())
            client_socket.shutdown(SHUT_RDWR)
            client_socket.close()

    try:
        fd = socket.fileno()
        while True:
            await ready(fd, READ)
            client_socket, address = socket.accept()
            client_socket.setblocking(0)
            connections[client_socket.fileno()] = spawn(connection_handler,
                                                        client_socket, address)
    finally:
        logging.info("Finishing echo listener on {}"
                     "".format(socket.getsockname()))
        socket.shutdown(SHUT_RDWR)
        socket.close()


if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    for socket in bind_sockets(22077, backlog=128):
        spawn(echo_acceptor, socket)
    run()
