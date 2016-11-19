"""
Implementation of the network primitives used coroutines for async I/O.
"""
import os
import socket
import logging

logger = logging.getLogger(__name__)


# utility functions


def bind_sockets(port, address=None, *,
                 family=socket.AF_UNSPEC,
                 backlog=128, flags=socket.AI_PASSIVE):
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
        raise RuntimeError("Cannot bind any sockets for {}".format(args))
    return results




