""" Utility functions.
"""
import os
import socket
import logging
from time import time

logger = logging.getLogger(__name__)


def timeout_gen(timeout):
    """ Timeouts generator.
    """
    assert ((isinstance(timeout, (int, float)) and timeout >= 0) or
            timeout is None)
    timeout = float(timeout or 0)
    deadline = time() + timeout if timeout else None
    while True:
        left_time = deadline - time()
        yield (None if deadline is None
               else (left_time if left_time > 0 else -1))


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


def pretty_addr(ip):
    """ Returns a pretty string representation of a given IP address.
    """
    if len(ip) > 2:
        return "[{}]:{}".format(*ip[:2])
    else:
        return "{}:{}".format(*ip)
