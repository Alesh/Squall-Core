""" Core utils
"""
import os
import errno
import socket
from time import time


class timeout_gen(object):
    """ Timeout generator
    """

    def __init__(self, initial_timeout):
        assert (isinstance(initial_timeout, (int, float)) or
                initial_timeout is None)
        self.deadline = None
        if initial_timeout is not None:
            self.deadline = time() + initial_timeout

    def __iter__(self):
        return self

    def __next__(self):
        if self.deadline is not None:
            value = self.deadline - time()
            return value if value > 0 else -1


class Addr(tuple):
    def __str__(self):
        """ Returns a pretty string representation of a given IP address.
        """
        if len(self) > 2:
            return "[{}]:{}".format(*self[:2])
        else:
            return "{}:{}".format(*self)


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
