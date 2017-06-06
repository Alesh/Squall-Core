""" Async network classes
"""
import errno
import socket
import logging
from .switching import Dispatcher
from .iostream import SocketStream
from .utils import bind_sockets


class TCPServer(object):
    """ Async TCP server
    """

    def __init__(self, stream_handler, block_size=1024, buffer_size=65536):
        self._disp = None  # type: Dispatcher
        self._sockets = dict()
        self._acceptors = dict()
        self._connections = dict()
        self._stream_handler = stream_handler
        self._stream_factory = (lambda disp, socket_:
                                SocketStream(disp, socket_, block_size, buffer_size))

    class _acceptor_factory(object):
        def __init__(self, disp, socket_, on_accept):
            def _acceptor(revents):
                if revents & disp.READ:
                    for _ in range(128):
                        try:
                            connection, address = socket_.accept()
                            on_accept(connection, address)
                        except socket.error as exc:
                            errno_ = getattr(0, 'errno', exc.args[0] if exc.args else 0)
                            if errno_ in (errno.EWOULDBLOCK, errno.EAGAIN):
                                return
                            if errno_ == errno.ECONNABORTED:
                                continue
                            logging.error("Exception while listening: %s", exc)

            handle = disp._loop.setup_io(_acceptor, socket_.fileno(), disp.READ)
            self._close = lambda *args: disp._loop.cancel_io(handle)

    def _accept(self, socket_, address):
        stream = self._stream_factory(self._disp, socket_)
        connection = self._disp.submit(self._stream_handler, stream, address)
        if connection.running():
            connection.add_done_callback(self._close)
            self._connections[connection] = stream
        else:
            stream.close()

    def _close(self, connection):
        stream = self._connections.pop(connection, None)
        if connection.running():
            connection.cancel()
        if stream is not None and stream.active:
            stream.close()

    def _close_all(self):
        for connection in tuple(self._connections.keys()):
            self._close(connection)

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
                acceptor = self._acceptor_factory(self._disp, socket_, self._accept)
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
                acceptor._close()
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
        self.before_start(self._disp)
        assert num_processes == 1  # ToDo: multiprocessed TCP server
        for (port, address), sockets in self._sockets.items():
            for socket_ in sockets:
                acceptor = self._acceptor_factory(self._disp, socket_, self._accept)
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
            self._close_all()
            self._disp.stop()
