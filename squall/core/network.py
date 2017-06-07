""" Async network classes
"""
import os
import errno
import socket
import logging
from functools import partial
from .switching import Dispatcher, Awaitable, READ, WRITE
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
                if revents & READ:
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

            handle = disp._loop.setup_io(_acceptor, socket_.fileno(), READ)
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


class TCPClient(object):
    """ Async TCP client
    """

    def __init__(self, disp, block_size=1024, buffer_size=65536):
        self._disp = disp
        self._stream_params = (block_size, buffer_size)

    def connect(self, stream_handler, address, *, timeout=None):
        """ See for detail `TCPClient.connect` """
        assert callable(stream_handler)
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))
        timeout = timeout if timeout >= 0 else -1
        return self._ConnectAwaitable(self, stream_handler, address, timeout)

    class _ConnectAwaitable(Awaitable):
        """ Awaitable for `TCPClient.connect`
        """

        def __init__(self, client, stream_handler, address, timeout):
            self._socket = None
            self._future = None
            self._client = client
            self._address = address
            self._stream_handler = stream_handler
            super().__init__(client._disp, address, timeout)

        def _on_connect(self, revents):

            def done_callback(future):
                try:
                    result = future.result()
                    self._callback(result if result is not None else True)
                except BaseException as exc:
                    self._callback(exc)

            self._cancel(*self._args)
            if revents == WRITE:
                # create connection
                disp = self._client._disp
                block_size, buffer_size = self._client._stream_params
                stream = SocketStream(disp, self._socket, block_size, buffer_size)
                self._future = disp.submit(self._stream_handler, stream, self._address)
                if self._future.done():
                    done_callback(self._future)
                else:
                    self._future.add_done_callback(done_callback)
            else:
                if self._socket is not None:
                    try:
                        self._socket.shutdown(socket.SHUT_RDWR)
                    except: pass
                    finally:
                        self._socket.close()
                if not isinstance(revents, BaseException):
                    revents = IOError("Some error while connect")
                self._callback(revents)

        def _setup(self, address, timeout):
            loop = self._client._disp._loop
            ready_handle = timeout_handle = None
            try:
                # self._socket = socket.socket(type=socket.SOCK_STREAM)
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.setblocking(0)
                self._socket.settimeout(0)
                if timeout < 0:
                    raise TimeoutError("I/O timeout")
                elif timeout > 0:
                    timeout_handle = loop.setup_timer(self._on_connect, timeout)
                self._socket.connect_ex(address)
                error = self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    raise(IOError(error, os.strerror(error)))
                ready_handle = loop.setup_io(self._on_connect, self._socket.fileno(), WRITE)
                return None, ready_handle, timeout_handle
            except Exception as exc:
                return exc, ready_handle, timeout_handle

        def _cancel(self, ready_handle=None, timeout_handle=None):
            loop = self._client._disp._loop
            if self._future is None:
                if ready_handle is not None:
                    loop.cancel_io(ready_handle)
                if timeout_handle is not None:
                    loop.cancel_timer(timeout_handle)
            else:
                # connection present
                if self._future.running():
                    self._future.cancel()
