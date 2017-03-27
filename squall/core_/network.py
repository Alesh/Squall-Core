""" Network classes
"""
import errno
import logging
import os
import socket
import sys
from functools import partial
from socket import SocketType, SHUT_RDWR

from squall.core.abc import StreamHandler
from squall.core.abc import TCPClient as AbcTCPClient
from squall.core.abc import TCPServer as AbcTCPServer
from squall.core_.abc import EventLoop, Callable
from squall.core_.iostream import IOStream, AutoBuffer
from squall.core_.switching import Dispatcher, SwitchedCoroutine


if sys.version_info[:2] > (3, 5):
    OnAccept = Callable[[SocketType, str], None]
else:
    OnAccept = Callable


def bind_sockets(port, address, *, backlog=127, reuse_port=False):
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


class _SocketAutoBuffer(AutoBuffer):
    """ Server socket auto buffer
    """

    def __init__(self, event_loop: EventLoop, socket_: SocketType, block_size, buffer_size):
        self._socket = socket_
        super().__init__(event_loop, socket_.fileno(), block_size, buffer_size)

    def _read_block(self, size):
        """ See for detail `AutoBuffer._read_block` """
        return self._socket.recv(size)

    def _write_block(self, block):
        """ See for detail `AutoBuffer._write_block` """
        return self._socket.send(block)

    def close(self):
        """ See for detail `AutoBuffer.close` """
        try:
            super().close()
            self._socket.shutdown(SHUT_RDWR)
        except:
            pass
        finally:
            self._socket.close()
            self._socket = None


class _SocketAcceptor(object):
    """ Socket acceptor
    """

    def __init__(self, event_loop: EventLoop, socket_: SocketType,
                 on_accept: OnAccept):

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
        self._handle = self._loop.setup_ready(acceptor, socket_.fileno(), self._loop.READ)

    def close(self):
        """ See more `AbcSocketAcceptor.close` """
        self._loop.cancel_ready(self._handle)


class _SocketStream(IOStream):
    """ Server socket stream
    """

    def __init__(self, disp: Dispatcher, socket_, block_size, buffer_size):
        socket_.setblocking(0)
        super().__init__(disp, _SocketAutoBuffer(disp._loop, socket_,
                                                 block_size, buffer_size))


class TCPServer(AbcTCPServer):
    """ Native implementation of the async TCP server
    """

    class ConnectionsManager(object):
        """ Connections manager / coroutine switcher
        """

        def __init__(self, disp: Dispatcher,
                     stream_handler: StreamHandler,
                     block_size: int, buffer_size: int):
            self._disp = disp
            self._connections = dict()
            self._block_size = block_size
            self._buffer_size = buffer_size
            self._stream_handler = stream_handler

        def accept(self, socket_: SocketType, address: str):
            """ Accepts incoming connection.
            """
            stream = _SocketStream(self._disp, socket_,
                                   self._block_size, self._buffer_size)
            future = self._disp.submit(self._stream_handler, stream, address)
            if future.running():
                future.add_done_callback(self.close)
                self._connections[future] = stream
            else:
                stream.close()

        def close(self, conn):
            """ Closes client connection
            """
            stream = self._connections.pop(conn, None)
            if conn.running():
                self._disp.switch(conn, GeneratorExit)
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
        """ See for detail `AbcTCPServer.active` """
        return self._disp is not None

    def bind(self, port, address=None, *, backlog=128, reuse_port=False):
        """ See for detail `AbcTCPServer.bind` """
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
        """ See for detail `AbcTCPServer.unbind` """
        if self.active:
            for acceptor in self._acceptors.pop((port, address), []):
                acceptor.close()
        elif (port, address) in self._sockets:
            self._sockets.pop((port, address))

    def before_start(self, disp):
        """ See for detail `AbcTCPServer.before_start` """

    def start(self, num_processes=1):
        """ See for detail `AbcTCPServer.start` """
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
        """ See for detail `AbcTCPServer.stop` """
        if self.active:
            self._sockets.clear()
            for (port, address) in tuple(self._acceptors.keys()):
                self.unbind(port, address)
            self._cm.close_all()
            self._disp.stop()


class TCPClient(AbcTCPClient):
    """ Native implementation of the async TCP client
    """

    def __init__(self, disp: Dispatcher, block_size=1024, buffer_size=65536):
        self._disp = disp
        self._stream_params = (block_size, buffer_size)

    def connect(self, stream_handler, host, port, *, timeout=None):
        """ See for detail `AbcTCPClient.connect` """
        return self._ConnectAwaitable(self._disp, stream_handler,
                                      host, port, timeout, *self._stream_params)

    class _ConnectAwaitable(SwitchedCoroutine):
        """ Awaitable for `TCPClient.connect` """

        def __init__(self, disp, stream_handler, host, port, timeout, block_size, buffer_size):
            self._disp = disp
            self._loop = disp._loop
            self._block_size = block_size
            self._buffer_size = buffer_size
            self._stream_handler = stream_handler
            timeout = timeout or 0
            timeout = timeout if timeout >= 0 else -1
            assert isinstance(timeout, (int, float))
            assert isinstance(host, str)
            assert isinstance(port, int)
            self._handles = []
            self._address = (host, port)
            super().__init__(disp, host, port, timeout)

        def on_connect(self, callback, socket_, revents):

            def done_callback(future):
                try:
                    result = future.result()
                    callback(result if result is not None else True)
                except BaseException as exc:
                    callback(exc)

            self.cancel()

            if isinstance(revents, Exception):
                try:
                    socket_.shutdown(SHUT_RDWR)
                except:
                    pass
                finally:
                    socket_.close()
                callback(ConnectionError("Cannon connect"))
            else:
                stream = _SocketStream(self._disp, socket_, self._block_size, self._buffer_size)
                future = self._disp.submit(self._stream_handler, stream, self._address)

                if future.done():
                    done_callback(future)
                else:
                    future.add_done_callback(done_callback)
                    self._handles.append(future)

        def setup(self, callback, host, port, timeout):
            timeout_exc = TimeoutError("I/O timeout")
            if timeout < 0:
                return timeout_exc
            try:
                socket_ = socket.socket()
                socket_.setblocking(0)
                socket_.settimeout(0)
                self._handles.append(self._loop.setup_ready(partial(self.on_connect, callback, socket_),
                                                            socket_.fileno(), self._loop.WRITE))
                if timeout > 0:
                    self._handles.append(self._loop.setup_timeout(partial(self.on_connect, callback, socket_),
                                                                  timeout, timeout_exc))
                else:
                    self._handles.append(None)
                try:
                    socket_.connect(self._address)
                except BlockingIOError:
                    pass
            except BaseException as exc:
                return exc

        def cancel(self):
            if len(self._handles) == 2:
                ready, timeout = self._handles
                self._loop.cancel_ready(ready)
                if timeout is not None:
                    self._loop.cancel_timeout(timeout)
            elif len(self._handles) == 1:
                future = self._handles[0]
                if future.running():
                    future.cancel()
            self._handles.clear()
