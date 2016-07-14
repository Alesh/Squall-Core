"""
This module contains basic classes and functions
for building asynchronous network applications.
"""
import errno
import socket
import logging

from squall import coroutine
from squall.coroutine import ERROR, READ, WRITE, TIMEOUT  # noqa
from squall.coroutine import ready, dispatcher,  _SwitchBack
from squall.utility import format_address, bind_sockets, bind_unix_socket  # noqa

try:
    from squall._squall import SocketAutoBuffer
except ImportError:
    from squall._autobuff import SocketAutoBuffer  # noqa


logger = logging.getLogger(__name__)


class IOStream(object):

    """ Base class for asynchronous I/O stream.
    """
    def __init__(self, auto_buffer):
        self._buffer = auto_buffer

    async def read_bytes(self, number, *, timeout=None):
        """ Asynchronously reads a number of bytes.
        """
        assert not self._buffer.closed
        assert isinstance(number, int) and number >= 0
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        number = (self._buffer.max_size
                  if number > self._buffer.max_size else number)

        def read_bytes_task(target, timeout):
            self._buffer.setup_read_bytes(target, None, number)
            if timeout > 0:
                dispatcher.setup_wait(target, timeout)

        done = self._buffer.check_read_bytes(None, number)
        if done:
            _, event, payload = done
            if event != ERROR:
                return payload
            else:
                raise payload
        try:
            return await _SwitchBack(read_bytes_task, timeout=(timeout or 0))
        except TimeoutError as exc:
            self._buffer.reset_task()
            raise exc

    async def read_until(self, delimiter, *, timeout=None, max_bytes=None):
        """ Asynchronously reads until we have found the given delimiter.
        """
        assert not self._buffer.closed
        assert isinstance(delimiter, bytes)
        assert (isinstance(max_bytes, int) and
                max_bytes >= 0) or max_bytes is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        max_bytes = (self._buffer.max_size
                     if max_bytes is None or max_bytes > self._buffer.max_size
                     else max_bytes)

        def read_until_task(target, timeout):
            self._buffer.setup_read_until(target, delimiter, max_bytes)
            if timeout > 0:
                dispatcher.setup_wait(target, timeout)

        done = self._buffer.check_read_until(None, delimiter, max_bytes)
        if done:
            _, event, payload = done
            if event != ERROR:
                return payload
            else:
                raise payload
        try:
            return await _SwitchBack(read_until_task, timeout=(timeout or 0))
        except TimeoutError as exc:
            self._buffer.reset_task()
            raise exc

    async def write(self, data=None, *, timeout=None, flush=False):
        """ Asynchronously writes outgoing data.
        """
        assert not self._buffer.closed
        assert isinstance(data, bytes) or data is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)

        result = 0
        if data:
            result = self._buffer.write(data)
            if (self._buffer.size < self._buffer.max_size / 4 and
               not flush):
                return

        def write_task(target, timeout):
            self._buffer.setup_write(target, result)
            if timeout > 0:
                dispatcher.setup_wait(target, timeout)

        done = self._buffer.check_write(None, result)
        if done:
            _, event, payload = done
            if event != ERROR:
                return payload
            else:
                raise payload
        try:
            return await _SwitchBack(write_task, timeout=(timeout or 0))
        except TimeoutError as exc:
            self._buffer.reset_task()
            raise exc

    def close(self):
        """ Closes stream.
        """
        if not self._buffer.closed:
            self._buffer.close()


class SocketStream(IOStream):

    """ Asynchronous socket stream.
    """

    def __init__(self, socket_, chunk_size=8192, buffer_size=262144):
        self.extra_info = dict(peername=socket_.getpeername(),
                               sockname=socket_.getsockname())
        self._buffer = SocketAutoBuffer(socket_, chunk_size, buffer_size)
        super(SocketStream, self).__init__(self._buffer)


class SocketAcceptor(object):

    """ Asynchronous socket connection acceptor.
    """

    def __init__(self, sockets,
                 connection_handler,
                 stream_factory=None):
        self._sockets = sockets
        self._listeners = list()
        self._close_socket = True
        self.connection_handler = connection_handler
        self.stream_factory = (stream_factory or
                               (lambda socket_: SocketStream(socket_)))

    async def _listener(self, listen_socket):
        connections = dict()
        logger.info("Established listener on %s",
                    format_address(listen_socket.getsockname()))

        async def _handler(connection):
            client_socket, address = connection
            try:
                stream = self.stream_factory(client_socket)
                await self.connection_handler(stream, address)
            finally:
                connections.pop(connection)
                stream.close()

        try:
            if self.connection_handler is None:
                raise RuntimeError("Connection handler is not defined")

            fd = listen_socket.fileno()
            listen_socket.setblocking(0)
            while True:
                await ready(fd, READ)
                repeat = 64
                while repeat:
                    repeat -= 1
                    try:
                        connection = listen_socket.accept()
                        connections[connection] = coroutine.spawn(_handler,
                                                                  connection)
                    except IOError as exc:
                        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                            break
                        elif exc.errno == errno.ECONNABORTED:
                            continue
                        raise exc
        finally:
            for coro in tuple(connections.values()):
                coro.close()
            logger.info("Finished listener on %s",
                        format_address(listen_socket.getsockname()))
            if self._close_socket:
                try:
                    listen_socket.shutdown(socket.SHUT_RDWR)
                finally:
                    listen_socket.close()

    def listen(self):
        """ Starts connection listening.
        """
        for socket_ in self._sockets:
            self._listeners.append(coroutine.spawn(self._listener, socket_))
        return len(self._listeners) > 0

    def close(self, close_socket=True):
        """ Closes listener.
        """
        self._close_socket = close_socket
        for listener in tuple(self._listeners):
            listener.close()
        self._listeners.clear()
