"""
This module contains basic classes and functions
for building asynchronous network applications.
"""
import errno
import socket
import logging
from signal import SIGINT, SIGTERM

from squall import coroutine
from squall.coroutine import ERROR, READ, WRITE, TIMEOUT  # noqa
from squall.coroutine import ready, dispatcher,  _SwitchBack
from squall.utility import format_address, bind_sockets, bind_unix_socket  # noqa

try:
    from squall._squall import SocketAutoBuffer
except ImportError:
    from squall._failback.autobuff import SocketAutoBuffer  # noqa


logger = logging.getLogger(__name__)
SIGNAL = dispatcher.SIGNAL


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
                 stream_factory=None,
                 close_socket=True):
        self._sockets = sockets
        self._listeners = list()
        self._close_socket = close_socket
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

    def close(self):
        """ Closes listener.
        """
        for listener in tuple(self._listeners):
            listener.close()
        self._listeners.clear()


class SocketServer(object):

    """ Asynchronous socket server.
    """
    def __init__(self):
        self._started = False
        self.__restarting = False
        self._bind_options = dict()

    @property
    def started(self):
        """ Returns `True` if server is started. """
        return self._started

    def bind(self, port, address=None, **kwargs):
        """ Binds socket with given parameters.
        """
        if isinstance(port, str):
            args = (port, )
            options = dict(mode=kwargs.get('mode', 0o600),
                           backlog=kwargs.get('backlog', 128))
        elif isinstance(port, int):
            args = (port, address)
            options = dict(family=kwargs.get('family', socket.AF_UNSPEC),
                           reuse_port=kwargs.get('reuse_port', False),
                           backlog=kwargs.get('backlog', 128),
                           flags=kwargs.get('flags'))
        else:
            raise ValueError("'port' has incorrect type")
        if args in self._bind_options:
            raise RuntimeError("Socket with given parameters already bind")
        self._bind_options[args] = options
        if self.started:
            self.__restarting = True
            self.stop()

    def unbind(self, port, address=None):
        """ Unbinds socket with given parameters.
        """
        if isinstance(port, str):
            args = (port, )
        elif isinstance(port, int):
            args = (port, address)
        else:
            raise ValueError("'port' has incorrect type")

        if args in self._bind_options:
            self._bind_options.pop(args)
            if self.started:
                self.__restarting = True
                self.stop()

    def start(self):
        """ Starts server.
        """
        if self.started:
            raise RuntimeError("Server has already started")
        while True:
            dispatcher.release_watching(self._event_handler)
            acceptors = dict()
            for args, options in self._bind_options.items():
                if len(args) == 2:
                    sockets = bind_sockets(*args, **options)
                else:
                    sockets = bind_unix_socket(*args, **options)
                acceptors[args] = SocketAcceptor(sockets,
                                                 self._stream_handler,
                                                 self._stream_factory)
            for args, acceptor in tuple(acceptors.items()):
                if not acceptor.listen():
                    logging.warning("cannot start listener for: %s",
                                    format_address(args))
                    acceptors.pop(args)
            if len(acceptors) == 0:
                raise RuntimeError("Cannot start server")
            dispatcher.setup_wait_signal(self._event_handler, SIGINT)
            dispatcher.setup_wait_signal(self._event_handler, SIGTERM)
            self._started = True
            dispatcher.start()
            self._started = False
            for args, acceptor in tuple(acceptors.items()):
                acceptor.close()
            if self.__restarting:
                self.__restarting = False
                continue
            break

    def stop(self):
        """ Stops server
        """
        if self.started:
            dispatcher.stop()

    def _event_handler(self, revents, payload):
        if revents == SIGNAL and payload in (SIGINT, SIGTERM):
            self.stop()

    def _stream_factory(self, socket_):
        return SocketStream(socket_)

    async def _stream_handler(self, stream, address):
        raise NotImplementedError
