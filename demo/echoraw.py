""" Sample "Echo server" based only on coroutine dispatcher
"""
import os
import sys
import errno
import socket
import logging
from signal import SIGINT
from squall.core import Dispatcher
from squall.core.utils import Addr, timeout_gen


def bind_sockets(port, address=None, *, backlog=127, reuse_port=False):
    """ Binds sockets """
    sockets = list()
    info = socket.getaddrinfo(address, port, socket.AF_INET,
                              socket.SOCK_STREAM, 0, socket.AI_PASSIVE)
    for *args, _, sockaddr in set(info):
        try:
            socket_ = socket.socket(*args)
        except socket.error as exc:
            if getattr(0, 'errno', exc.args[0] if exc.args else 0) == errno.EAFNOSUPPORT:
                continue
            raise
        if reuse_port:
            if not hasattr(socket, "SO_REUSEPORT"):
                raise ValueError("the platform doesn't support SO_REUSEPORT")
            socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        if os.name != 'nt':
            socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socket_.setblocking(0)
        socket_.bind(sockaddr)
        socket_.listen(backlog)
        sockets.append(socket_)
    return sockets


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
