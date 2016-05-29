"""
Basics asynchronous network
===========================
"""
import errno
import socket
import logging
from time import time as now
from collections import deque

from tornado import gen
from tornado.ioloop import IOLoop
from tornado.concurrent import Future
from tornado.netutil import bind_sockets  # noqa
if hasattr(socket, 'AF_UNIX'):
    from tornado.netutil import bind_unix_socket  # noqa

from squall.coroutine import spawn, ready, READ, WRITE, ERROR  # noqa


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


class SocketStream(object):

    """ Asynchronous socket stream.
    """

    def __init__(self, socket_, chunk_size=8192, buffer_size=262144):
        self._mask = 0
        self._exc = None
        self._task = None
        self._inbuff = b''
        self._outbuff = b''
        self._active = True
        self._socket = socket_
        self._fd = socket_.fileno()
        self._socket.setblocking(0)
        self._loop = IOLoop.current()
        self.extra_info = dict(peername=socket_.getpeername(),
                               sockname=socket_.getsockname())
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size
        self.running = READ

    @property
    def closed(self):
        """ Return true if cstreram is closed. """
        return not self._active

    @property
    def running(self):
        """ Autobuffering state. """
        return self._mask

    @running.setter
    def running(self, value):
        prev_mask = self._mask
        if value < 0 and (value & self._mask) == value:
            self._mask = self._mask ^ value
        elif value > 0:
            self._mask = self._mask | value
        else:
            self._mask = 0
        if prev_mask != self._mask:

            if self._mask > 0:
                if prev_mask == 0:
                    self._loop.add_handler(self._fd, self._callback, self._mask)
                else:
                    self._loop.update_handler(self._fd, self._mask)
            else:
                self._loop.remove_handler(self._fd)

    def _callback(self, fd, events):
        if ERROR & events:
            self._exc = IOError("Unexpected I/O loop error")
            self.running = 0
        else:
            try:
                if READ & events:
                    data = self._socket.recv(self.chunk_size)
                    if len(data) > 0:
                        self._inbuff += data
                        if len(self._inbuff) >= self.buffer_size:
                            self.running = -READ
                    else:
                        self._exc = ConnectionResetError(
                            errno.ECONNRESET, "Connection reset by peer")
                if WRITE & events and len(self._outbuff) > 0:
                    sent = self._socket.send(self._outbuff[:self.chunk_size])
                    if sent > 0:
                        self._outbuff = self._outbuff[sent:]
                        if len(self._outbuff) == 0:
                            self.running = -WRITE
                    else:
                        self._exc = ConnectionResetError(
                            errno.ECONNRESET, "Connection reset by peer")
            except IOError as exc:
                self._exc = exc
        done = self._task()
        if done:
            self._task = None
            callable, arg = done
            callable(arg)

    async def read_bytes(self, number, *, timeout=None):
        """ Asynchronously reads a number of bytes.
        """
        assert self._active
        assert self._task is None
        assert isinstance(number, int) and number >= 0
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        future = Future()
        number = self.buffer_size if number > self.buffer_size else number

        def _check_done():
            if self._exc is not None:
                exc, self._exc = self._exc, None
                return future.set_exception, exc
            elif len(self._inbuff) >= number:
                data = self._inbuff[:number]
                self._inbuff = self._inbuff[number:]
                return future.set_result, data
            return None

        def _read_bytes():
            self.running = READ
            self._task = _check_done
            if timeout:
                deadline = now() + timeout
                return gen.with_timeout(deadline, future, self._loop)
            else:
                return future

        done = _check_done()
        if done:
            self._task = None
            _, result = done
            return result
        try:
            return await _read_bytes()
        except gen.TimeoutError:
            self._task = None
            raise TimeoutError(errno.ETIMEDOUT, "I/O timed out")

    async def read_until(self, delimiter, *, timeout=None, max_bytes=None):
        """ Asynchronously reads until we have found the given delimiter.
        """
        assert self._active
        assert self._task is None
        assert isinstance(delimiter, bytes)
        assert (isinstance(max_bytes, int) and
                max_bytes >= 0) or max_bytes is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)

        future = Future()
        max_bytes = (self.buffer_size
                     if max_bytes is None or max_bytes > self.buffer_size
                     else max_bytes)

        def _check_done():
            if self._exc is not None:
                exc, self._exc = self._exc, None
                return future.set_exception, exc
            else:
                pos = self._inbuff.find(delimiter)
                if pos >= 0:
                    pos += len(delimiter)
                    data = self._inbuff[:pos]
                    self._inbuff = self._inbuff[pos:]
                    return future.set_result, data
                elif len(self._inbuff) >= max_bytes:
                    data = self._inbuff[:max_bytes]
                    self._inbuff = self._inbuff[max_bytes:]
                    return future.set_result, data
            return None

        def _read_until():
            self.running = READ
            self._task = _check_done
            if timeout:
                deadline = now() + timeout
                return gen.with_timeout(deadline, future, self._loop)
            else:
                return future

        done = _check_done()
        if done:
            self._task = None
            _, result = done
            return result
        try:
            return await _read_until()
        except gen.TimeoutError:
            self._task = None
            raise TimeoutError(errno.ETIMEDOUT, "I/O timed out")

    async def write(self, data=None, *, timeout=None, flush=False):
        """ Asynchronously writes outgoing data.
        """
        assert self._active
        assert self._task is None
        assert isinstance(data, bytes) or data is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)

        future = Future()
        if data:
            self._outbuff += data
            if (len(self._outbuff) < self.buffer_size / 4 and not flush):
                return

        def _check_done():
            if self._exc is not None:
                exc, self._exc = self._exc, None
                return future.set_exception, exc
            else:
                if len(self._outbuff) == 0:
                    return future.set_result, None
            return None

        def _write():
            self.running = WRITE
            self._task = _check_done
            if timeout:
                deadline = now() + timeout
                return gen.with_timeout(deadline, future, self._loop)
            else:
                return future

        done = _check_done()
        if done:
            self._task = None
            _, result = done
            return result
        try:
            return await _write()
        except gen.TimeoutError:
            self._task = None
            raise TimeoutError(errno.ETIMEDOUT, "I/O timed out")

    def close(self):
        """ Closes stream.
        """
        if self._active:
            if self._socket:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except IOError:
                    pass
                finally:
                    self._socket.close()
            self._active = False


class SocketAcceptor(object):

    """ Asynchronous socket connection acceptor.
    """

    def __init__(self, sockets, stream_factory=None):
        self._sockets = sockets
        self._listeners = deque()
        self.stream_factory = (stream_factory or
                               (lambda socket_: SocketStream(socket_)))

    async def _listener(self, listen_socket):
        connections = dict()
        logging.info("Established listener on {}"
                     "".format(listen_socket.getsockname()))

        async def _serve(connection):
            client_socket, address = connection
            try:
                stream = self.stream_factory(client_socket)
                await self.handle_connection(stream, address)
            finally:
                connections.pop(connection)
                stream.close()

        try:
            fd = listen_socket.fileno()
            while True:
                await ready(fd, READ)
                repeat = 64
                while repeat:
                    repeat -= 1
                    try:
                        connection = listen_socket.accept()
                        connections[connection] = spawn(_serve, connection)
                    except IOError as exc:
                        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                            break
                        elif exc.errno == errno.ECONNABORTED:
                            continue
                        raise exc

        finally:
            logging.info("Finished listener on {}"
                         "".format(listen_socket.getsockname()))
            listen_socket.shutdown(socket.SHUT_RDWR)
            listen_socket.close()

    async def handle_connection(self, stream, address):
        """ Handles a new incoming connection.
        """

    def listen(self):
        """ Starts connection listening.
        """
        for socket_ in self._sockets:
            self._listeners.append(spawn(self._listener, socket_))

    def cloase(self):
        """ Closes listener.
        """
        while self._listeners:
            listener = self._listeners.popleft()
            listener.close()
