""" Sample "Echo server" based only on coroutine dispatcher
"""
import os
import sys
import errno
import socket
import logging
from signal import SIGINT
from squall.core import Dispatcher
from squall.core.utils import Addr, timeout_gen, bind_sockets


async def echo_handler(disp, connection_socket, addr):
    """ Connections handler """
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
        logging.warning("[%s]Connection fail: %s", addr, exc)


async def echo_acceptor(disp, listen_socket):
    """ Connections acceptor """
    connections = dict()
    listen_socket.setblocking(0)
    fileno = listen_socket.fileno()
    addr = Addr(listen_socket.getsockname())
    logging.info("[%s]Established echo listener", addr)

    async def serve_connection(disp, connection_socket, address):
        """ Function used to build connection coroutine"""
        addr = Addr(address)
        key = (connection_socket, address)
        connection_socket.setblocking(0)
        logging.info("[%s]Accepted connection", addr)
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
            logging.info("[%s]Connection has closed", addr)

    try:
        while True:
            await disp.ready(fileno, disp.READ)
            while True:
                try:
                    args = listen_socket.accept()
                    connections[args] = disp.submit(serve_connection, *args)
                except IOError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        break
                    raise exc

    except IOError as exc:
        logging.error("[%s]Listenner fail: %s", addr, exc)
    finally:
        logging.info("[%s]Finished echo listener", addr)
        try:
            listen_socket.shutdown(socket.SHUT_RDWR)
        except IOError:
            pass
        finally:
            listen_socket.close()


async def terminator(disp):
    """ Terminates server by system signal. """
    try:
        await disp.signal(SIGINT)
        print("Got SIGINT!")
    finally:
        disp.stop()


def main():
    """ Starts server """
    disp = Dispatcher()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    for socket_ in bind_sockets(port):
        disp.submit(echo_acceptor, socket_)
    disp.submit(terminator)
    disp.start()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
