""" Module of callback classes based on asyncio
"""
import asyncio
import errno
import logging
import os
import socket
from socket import SocketType

from squall.core.native.cb.abc import AutoBuffer as AbcAutoBuffer
from squall.core.native.cb.abc import EventLoop as AbcEventLoop
from squall.core.native.cb.abc import SocketAcceptor as AbcSocketAcceptor


class EventLoop(AbcEventLoop):
    """ asyncio based implementation of `squall.core.native.cb.abc.EventLoop`
    """

    READ = 1
    WRITE = 2

    def __init__(self):
        self._signals = dict()
        self._loop = asyncio.get_event_loop()
        super().__init__()

    def start(self):
        """ See more: `AbcEventLoop.start` """
        logging.info("Using asyncio based callback classes")
        self._loop.run_forever()

    def stop(self):
        """ See more: `AbcEventLoop.stop` """
        self._loop.stop()

    def setup_timeout(self, callback, seconds, result=True):
        """ See more: `AbcEventLoop.setup_timeout` """
        deadline = self._loop.time() + seconds
        return self._loop.call_at(deadline, callback, result)

    def cancel_timeout(self, handle):
        """ See more: `AbcEventLoop.cancel_timeout` """
        handle.cancel()

    def setup_ready(self, callback, fd, events):
        """ See more: `AbcEventLoop.setup_ready` """
        if events & self.READ:
            self._loop.add_reader(fd, callback, self.READ)
        if events & self.WRITE:
            self._loop.add_writer(fd, callback, self.WRITE)
        return fd, events

    def cancel_ready(self, handle):
        """ See more: `AbcEventLoop.cancel_ready` """
        fd, events = handle
        if events & self.READ:
            self._loop.remove_reader(fd)
        if events & self.WRITE:
            self._loop.remove_writer(fd)

    def _handle_signal(self, signum):
        for callback in tuple(self._signals[signum]):
            self._loop.call_soon(callback, signum)

    def setup_signal(self, callback, signum):
        """ See more: `AbcEventLoop.setup_signal` """
        if signum not in self._signals:
            self._loop.add_signal_handler(signum, self._handle_signal, signum)
            self._signals[signum] = list()
        self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handler):
        """ See more: `AbcEventLoop.cancel_signal` """
        signum, callback = handler
        if signum in self._signals:
            self._signals[signum].remove(callback)


class SocketAutoBuffer(AbcAutoBuffer, asyncio.Protocol):
    """ asyncio based implementation of `squall.core.native.cb.abc.AutoBuffer` for socket
    """

    READ = 1
    WRITE = 2

    def __init__(self, event_loop: EventLoop, socket_: SocketType, block_size, buffer_size):
        self._in = b''
        self._task = None
        self._reading = True
        self._writing = True
        self._transport = None  # type: asyncio.Transport
        self._loop = event_loop._loop  # type: asyncio.AbstractEventLoop
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._active = self._loop.create_connection(lambda: self, sock=socket_)
        next(self._active)

    def connection_made(self, transport):
        """ See more: `asyncio.BaseProtocol.connection_made` """
        self._transport = transport
        self._transport.set_write_buffer_limits(self._buffer_size, self._buffer_size / 2)

    def connection_lost(self, exc):
        """ See more: `asyncio.BaseProtocol.connection_lost` """
        self._event_handler(exc or ConnectionAbortedError("Connection reset by host"))
        self._active = None

    def data_received(self, data):
        """ See more: `asyncio.Protocol.data_received` """
        self._in += data
        self._event_handler(self.READ)

    def eof_received(self):
        """ See more: `asyncio.Protocol.eof_received` """
        self._event_handler(ConnectionResetError("Connection reset by peer"))

    def resume_writing(self):
        """ See more: `asyncio.BaseProtocol.resume_writing` """
        self._writing = True

    def pause_writing(self):
        """ See more: `asyncio.BaseProtocol.pause_writing` """
        self._writing = False

    def _event_handler(self, revents):
        last_error = None
        if isinstance(revents, Exception):
            last_error = revents

        if self._task is not None:
            # apply buffer task
            result = None
            callback, event, method, timeout = self._task
            if last_error is not None:
                result = last_error
            elif event & revents:
                if event == self.READ:
                    result = method(self._in)
                elif event == self.WRITE:
                    result = method(self._transport.get_write_buffer_size())
            if result is not None:
                self.cancel_task()
                callback(result)
            else:
                if event == self.WRITE:
                    self._loop.call_soon(self._event_handler, self.WRITE)

        if self.active:
            # recalc I/O mode
            if self._reading and len(self._in) >= self._buffer_size:
                self._reading = False
                self._transport.pause_reading()
            elif not self._reading and len(self._in) < self._buffer_size:
                self._reading = True
                self._transport.resume_reading()

    @property
    def active(self):
        """ See more: `AbcAutoBuffer.active` """
        return self._active is not None

    @property
    def block_size(self):
        """ See more: `AbcAutoBuffer.block_size` """
        return self._block_size

    @property
    def buffer_size(self):
        """ See more: `AbcAutoBuffer.buffer_size` """
        return self._buffer_size

    def setup_task(self, callback, event, method, timeout=None):
        result = None
        if event == self.READ:
            result = method(self._in)
        elif event == self.WRITE:
            result = method(self._transport.get_write_buffer_size())
        if result is None:
            if timeout > 0:
                deadline = self._loop.time() + timeout
                timeout = self._loop.call_at(deadline, self._event_handler, TimeoutError("I/O timeout"))
                if event == self.WRITE:
                    self._loop.call_soon(self._event_handler, self.WRITE)
            else:
                timeout = None
            self._task = (callback, event, method, timeout)
        return result

    def cancel_task(self):
        if self._task is not None:
            callback, event, method, timeout = self._task
            if timeout is not None:
                timeout.cancel()
            self._task = None

    def read(self, max_bytes):
        """ See more: `AbcAutoBuffer.read` """
        result, self._in = self._in[:max_bytes], self._in[max_bytes:]
        return result

    def write(self, data):
        """ See more: `AbcAutoBuffer.write` """
        if self.active and self._writing:
            self._transport.write(data)
            return len(data)
        return 0

    def close(self):
        """ See more: `AbcAutoBuffer.close` """
        if self.active:
            self._transport.abort()


class SocketAcceptor(AbcSocketAcceptor):
    """ asyncio based implementation of `squall.core.native.cb.abc.SocketAcceptor` for socket
    """
    READ = 1

    def __init__(self, event_loop, socket_, on_accept):

        def acceptor(revents):
            if revents & self.READ:
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

        self._fd = socket_.fileno()
        self._loop = event_loop._loop
        self._loop.add_reader(self._fd, acceptor, self.READ)

    def close(self):
        """ See more `AbcSocketAcceptor.close` """
        self._loop.remove_reader(self._fd)


def bind_sockets(port, address, *, backlog=127, reuse_port=False):
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
