"""
Utility classes and functions.
"""
import os
import stat
import errno
import socket
import logging
from time import time as now


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


def format_address(addr):
    """ Represents IP address as string.
    """
    result = str(addr)
    if isinstance(addr, (tuple, list)):
        if len(addr) == 2:
            result = "{}:{}".format(*addr)
        elif len(addr) == 4:
            result = "[{}]:{}".format(*addr[:2])
        elif len(addr) == 1:
            result = str(addr[0])
    return result


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


bind_unix_socket = None
if hasattr(socket, 'AF_UNIX'):

    def bind_unix_socket(file, mode=0o600, backlog=128):
        """Creates a listening unix socket.
        """
        socket_ = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            st = os.stat(file)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise
        else:
            if stat.S_ISSOCK(st.st_mode):
                os.remove(file)
            else:
                raise ValueError("Cannot create unix socket, file with"
                                 " the same name '%s' already exists", file)
        socket_.bind(file)
        os.chmod(file, mode)
        socket_.listen(backlog)
        return [socket_]
