""" Async echo server based on low level functions.
"""
import os
import errno
import logging
import socket
from time import time as now
from socket import SHUT_RDWR

from squall import coroutine
from squall.coroutine import wait_io, READ, WRITE


def timeout_gen(timeout):
    """ Timeout generator.
    """
    assert ((isinstance(timeout, (int, float)) and timeout >= 0) or
            timeout is None)
    timeout = float(timeout or 0)
    deadline = now() + timeout if timeout else None
    while True:
        yield (None if deadline is None
               else (deadline - now()
                     if deadline - now() > 0 else 0.000000001))


def bind_sockets(port, address=None, family=socket.AF_UNSPEC,
                 backlog=128, reuse_port=False, flags=None):
    """ Creates and returns a list of all listening sockets
    """
    if reuse_port and not hasattr(socket, "SO_REUSEPORT"):
        raise ValueError("the platform doesn't support SO_REUSEPORT")
    sockets = []
    if address == "":
        address = None
    if flags is None:
        flags = socket.AI_PASSIVE
    for (af, socktype, proto, canonname, sockaddr) \
            in set(socket.getaddrinfo(address, port, family,
                                      socket.SOCK_STREAM, 0, flags)):
        try:
            socket_ = socket.socket(af, socktype, proto)
        except socket.error:
            logging.error("Cannot bind socket for socket paremeters:"
                          " {}".format((af, socktype, proto)))
            continue
        if os.name != 'nt':
            socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if reuse_port:
            socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        if af == socket.AF_INET6:
            if hasattr(socket, "IPPROTO_IPV6"):
                socket_.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        socket_.bind(sockaddr)
        socket_.listen(backlog)
        sockets.append(socket_)
    if len(sockets) == 0:
        raise ValueError("Cannon bind any sockets for function args: %s"
                         (port, address, family, backlog, flags, reuse_port))
    return sockets


async def echo_handler(socket_, address):
    fd = socket_.fileno()
    logging.info("Accepted connection: {}".format(address))
    try:
        while True:
            tg = timeout_gen(15)
            await wait_io(fd, READ, timeout=next(tg))
            data = socket_.recv(1024)
            if data:
                await wait_io(fd, WRITE, timeout=next(tg))
                socket_.send(data)
            else:
                raise ConnectionResetError(errno.ECONNRESET,
                                           "Connection reset by peer")
    except IOError as exc:
        logging.warning("Connection from {}: {}".format(address, exc))
    finally:
        logging.info("Connection from {} closed.".format(address))


async def echo_acceptor(socket_):
    connections = dict()
    logging.info("Established echo listener on {}"
                 "".format(socket_.getsockname()))
    socket_.setblocking(0)

    async def _serve(connection):
        client_socket, address = connection
        client_socket.setblocking(0)
        try:
            await echo_handler(client_socket, address)
        finally:
            connections.pop(connection)
            if client_socket:
                try:
                    client_socket.shutdown(socket.SHUT_RDWR)
                finally:
                    client_socket.close()
    try:
        fd = socket_.fileno()
        while True:
            await wait_io(fd, READ)
            while True:
                try:
                    conn = socket_.accept()
                    connections[conn] = coroutine.spawn(_serve, conn)
                except IOError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        break
                    raise exc

    finally:
        logging.info("Finished echo listener on {}"
                     "".format(socket_.getsockname()))
        socket_.shutdown(SHUT_RDWR)
        socket_.close()


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    for socket_ in bind_sockets(22077, backlog=128):
        coroutine.spawn(echo_acceptor, socket_)
    coroutine.run()
