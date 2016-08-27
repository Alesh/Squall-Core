"""
This module contains basic classes and functions
for building asynchronous network applications.
"""
import os
import stat
import time
import errno
import socket
import logging

from squall import coroutine
from squall.coroutine import READ
from squall.stream import SocketStream

logger = logging.getLogger(__name__)


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


def timeout_gen(timeout):
    """ Timeout generator.
    """
    assert ((isinstance(timeout, (int, float)) and timeout >= 0) or
            timeout is None)
    now = time.time
    timeout = float(timeout or 0)
    deadline = now() + timeout if timeout else None
    while True:
        yield (None if deadline is None
               else (deadline - now()
                     if deadline - now() > 0 else 0.000000001))


class Binding(object):

    """ Base sockets building.
    """

    def __init__(self, sockets):
        assert all(isinstance(socket_, socket.socket) for socket_ in sockets)
        self._sockets = sockets

    @property
    def active(self):
        return len(self._sockets) > 0

    @property
    def sockets(self):
        return self._sockets

    def close(self):
        for socket_ in self._sockets:
            try:
                socket_.shutdown(socket.SHUT_RDWR)
            finally:
                socket_.close()
        self._sockets.clear()


class StreamBinding(Binding):

    """ Stream base sockets building.
    """

    def __init__(self, sockets, backlog):
        for socket_ in sockets:
            socket_.listen(backlog)
        super(StreamBinding, self).__init__(sockets)


class TcpBinding(StreamBinding):

    """ TCP/IP stream sockets building.
    """

    def __init__(self, port, address=None,
                 backlog=128, family=None, reuse_port=False, flags=None):
        sockets = []
        assert isinstance(port, int)
        address = address or None
        flags = flags or socket.AI_PASSIVE
        family = family or socket.AF_UNSPEC
        if reuse_port and not hasattr(socket, "SO_REUSEPORT"):
            logger.error("the platform doesn't support SO_REUSEPORT")
        else:
            for ai in set(socket.getaddrinfo(address, port, family,
                                             socket.SOCK_STREAM, 0, flags)):
                try:
                    socket_ = socket.socket(*ai[:3])
                except socket.error:
                    logger.error("Cannot bind socket for socket paremeters:"
                                 " {}".format(ai[:3]))
                    continue
                if os.name != 'nt':
                    socket_.setsockopt(socket.SOL_SOCKET,
                                       socket.SO_REUSEADDR, 1)
                if reuse_port:
                    socket_.setsockopt(socket.SOL_SOCKET,
                                       socket.SO_REUSEPORT, 1)
                if ai[0] == socket.AF_INET6:
                    if hasattr(socket, "IPPROTO_IPV6"):
                        socket_.setsockopt(socket.IPPROTO_IPV6,
                                           socket.IPV6_V6ONLY, 1)
                socket_.bind(ai[4])
                sockets.append(socket_)
        super(TcpBinding, self).__init__(sockets, backlog)


class UnixBinding(Binding):

    """ Unix stream sockets building.
    """

    def __init__(self, file, mode=0o600, backlog=128):
        sockets = []
        assert isinstance(file, str)
        socket_ = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            try:
                st = os.stat(file)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise
            else:
                if stat.S_ISSOCK(st.st_mode):
                    os.remove(file)
                else:
                    raise FileExistsError("Cannot create unix socket, file with"
                                          " the same name '%s' already exists",
                                          file)
            socket_.bind(file)
            os.chmod(file, mode)
            sockets.append(socket_)
        except Exception as exc:
            logger.error(exc.msg)
        super(UnixBinding, self).__init__(sockets, backlog)


class ConnectionAcceptor(object):

    """ Network connection acceptor
    """

    def __init__(self, binding,
                 on_connect, connection_factory=None,
                 on_listen=None, on_finish=None, on_close=None):
        self._listeners = dict()
        self._binding = binding
        self._on_connect = on_connect
        self._connection_factory = connection_factory or (lambda A: A)
        self._on_listen = on_listen or self.__on_listen
        self._on_finish = on_finish or self.__on_finish
        self._on_close = on_close or self.__on_close

    def listen(self):
        """ Starts connection listening.
        """
        for socket_ in self._binding.sockets:
            self._listeners[socket_] = coroutine.spawn(self._listener, socket_)
        return len(self._listeners) > 0

    def close(self):
        """ Closes listener.
        """
        for socket_, listener in tuple(self._listeners):
            listener.close()

    async def _listener(self, listen_socket):
        connections = dict()

        async def connection_handler(connection, address):
            try:
                await self._on_connect(connection, address)
            finally:
                connections.pop(connection)

        try:
            fd = listen_socket.fileno()
            listen_socket.setblocking(0)
            while True:
                await coroutine.wait_io(fd, READ)
                attempts = 16
                while attempts:
                    attempts -= 1
                    try:
                        client_socket, address = listen_socket.accept()
                        connection = self._connection_factory(client_socket)
                        connections[connection] = coroutine.spawn(
                            connection_handler, connection, address)
                    except IOError as exc:
                        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                            break
                        elif exc.errno == errno.ECONNABORTED:
                            continue
                        raise exc
        finally:
            for coro_connection_handler in tuple(connections.values()):
                coro_connection_handler.close()
            self._on_finish(listen_socket)
            self._listeners.pop(listen_socket)
            if len(self._listeners) == 0:
                self._on_close()

    def __on_listen(self, socket_):
        logger.info("Established listener on %s",
                    format_address(socket_.getsockname()))

    def __on_finish(self, socket_):
        logger.info("Finished listener on %s",
                    format_address(socket_.getsockname()))

    def __on_close(self):
        self._binding.close()


class SocketStreamAcceptor(ConnectionAcceptor):

    """ Network socket stream acceptor
    """

    def __init__(self, binding,
                 on_connect, connection_factory=None,
                 on_listen=None, on_finish=None, on_close=None):
        connection_factory = (connection_factory or
                              (lambda socket_: SocketStream(socket_)))
        super(SocketStreamAcceptor, self).__init__(binding, on_connect,
                                                   connection_factory,
                                                   on_listen, on_finish,
                                                   on_close)
