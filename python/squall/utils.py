""" Utility functions.
"""
import os
import socket
import logging
from time import time

logger = logging.getLogger(__name__)


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
            return value if value >= 0 else -1


def bind_sockets(port, address=None, *, backlog=128,
                 family=socket.AF_UNSPEC, flags=socket.AI_PASSIVE):
    """ Creates, prepares to use and returns sockets corresponding
    to given parameters.
    """
    results = list()
    for args in set(socket.getaddrinfo(address or None, port, family,
                                       socket.SOCK_STREAM, 0, flags)):
        try:
            socket_ = socket.socket(*args[:3])
            if os.name != 'nt':
                socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if args[0] == socket.AF_INET6 and hasattr(socket, "IPPROTO_IPV6"):
                socket_.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        except socket.error:
            logger.error("Cannot bind socket for: {}".format(args[:3]))
            continue
        socket_.bind(args[4])
        socket_.listen(backlog)
        results.append(socket_)
    if len(results) == 0:
        raise IOError("Cannot bind any sockets for {}".format(args))
    return results


class Addr(tuple):

    def __str__(self):
        """ Returns a pretty string representation of a given IP address.
        """
        if len(self) > 2:
            return "[{}]:{}".format(*self[:2])
        else:
            return "{}:{}".format(*self)
