""" Async network classes
"""
import os
import errno
import socket
import logging
from functools import partial
from squall.core.switching import Dispatcher, _Awaitable
from squall.core.iostream import IOStream

try:
    from squall.core_cython import SocketAutoBuffer
except ImportError:
    from squall.core_fallback import SocketAutoBuffer  # noqa


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
    for af, socktype, proto, canonname, sockaddr in set(info):
        try:
            socket_ = socket.socket(af, socktype, proto)
        except socket.error as e:
            if getattr(0, 'errno', e.args[0] if e.args else 0) == errno.EAFNOSUPPORT:
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


class _SocketAcceptor(object):
    """ Socket acceptor
    """

    def __init__(self, event_loop, socket_, on_accept):

        def acceptor(revents):
            if revents & event_loop.READ:
                for _ in range(128):
                    try:
                        connection, address = socket_.accept()
                        on_accept(connection, address)
                    except socket.error as e:
                        errno_ = getattr(0, 'errno', e.args[0] if e.args else 0)
                        if errno_ in (errno.EWOULDBLOCK, errno.EAGAIN):
                            return
                        if errno_ == errno.ECONNABORTED:
                            continue
                        logging.error("Exception while listening: {}".format(e))

        self._loop = event_loop
        self._handle = self._loop.setup_io(acceptor, socket_.fileno(), self._loop.READ)

    def close(self):
        """ See more `AbcSocketAcceptor.close` """
        self._loop.cancel_io(self._handle)


class _SocketStream(IOStream):
    """ Server socket stream
    """

    def __init__(self, disp, socket_, block_size, buffer_size):
        super().__init__(SocketAutoBuffer(disp._loop, socket_,
                                          block_size, buffer_size))


class TCPServer(object):
    """ Async TCP server
    """

    class ConnectionsManager(object):
        """ Connections manager / coroutine switcher
        """

        def __init__(self, disp, stream_handler,
                     block_size: int, buffer_size: int):
            self._disp = disp
            self._connections = dict()
            self._block_size = block_size
            self._buffer_size = buffer_size
            self._stream_handler = stream_handler

        def accept(self, socket_, address):
            """ Accepts incoming connection.
            """
            stream = _SocketStream(self._disp, socket_,
                                   self._block_size, self._buffer_size)
            core_conn = self._disp.submit(self._stream_handler, stream, address)
            if core_conn.running():
                core_conn.add_done_callback(self.close)
                self._connections[core_conn] = stream
            else:
                stream.close()

        def close(self, conn):
            """ Closes client connection
            """
            stream = self._connections.pop(conn, None)
            if conn.running():
                conn.cancel()
            if stream is not None and stream.active:
                stream.close()

        def close_all(self):
            """ Closes all client connection
            """
            for conn in tuple(self._connections.keys()):
                self.close(conn)

    def __init__(self, stream_handler, block_size=1024, buffer_size=65536):
        self._disp = None  # type: Dispatcher
        self._sockets = dict()
        self._acceptors = dict()
        self._cm = None  # type: self.ConnectionsManager
        self._cm_args = (stream_handler, block_size, buffer_size)

    @property
    def active(self):
        """ Returns `True` if this server is active (not stopped).
        """
        return self._disp is not None

    def bind(self, port, address=None, *, backlog=128, reuse_port=False):
        """ Binds this server to the given port on the given address.
        """
        for socket_ in bind_sockets(port, address, backlog=backlog, reuse_port=reuse_port):
            if self.active:
                acceptor = _SocketAcceptor(self._disp._loop, socket_, self._cm.accept)
                if (port, address) not in self._acceptors:
                    self._acceptors[(port, address)] = list()
                self._acceptors[(port, address)].append(acceptor)
            else:
                if (port, address) not in self._sockets:
                    self._sockets[(port, address)] = list()
                self._sockets[(port, address)].append(socket_)

    def unbind(self, port, address=None):
        """ Unbinds this server from the given port on the given address.
        """
        if self.active:
            for acceptor in self._acceptors.pop((port, address), []):
                acceptor.close()
        elif (port, address) in self._sockets:
            self._sockets.pop((port, address))

    def before_start(self, disp):
        """ Called before starting this server.

        May be overridden to initialize and start other coroutines there.
        """

    def start(self, num_processes=1):
        """ Starts this server.
        """
        self._disp = Dispatcher()
        self._cm = self.ConnectionsManager(self._disp, *self._cm_args)
        self.before_start(self._disp)
        assert num_processes == 1  # ToDo: multiprocessed TCP server
        for (port, address), sockets in self._sockets.items():
            for socket_ in sockets:
                acceptor = _SocketAcceptor(self._disp._loop, socket_, self._cm.accept)
                if (port, address) not in self._acceptors:
                    self._acceptors[(port, address)] = list()
                self._acceptors[(port, address)].append(acceptor)
        self._sockets.clear()
        self._disp.start()
        self._disp = None

    def stop(self):
        """ Stops this server.
        """
        if self.active:
            self._sockets.clear()
            for (port, address) in tuple(self._acceptors.keys()):
                self.unbind(port, address)
            self._cm.close_all()
            self._disp.stop()
