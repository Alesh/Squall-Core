"""
Basics asynchronous network
===========================
"""
import os
import stat
import errno
import socket
import logging
from time import time as now
from collections import deque
from functools import partial

try:
    from squall import _squall as dispatcher
    from squall._squall import ERROR, READ, WRITE
except ImportError:
    from squall import _tornado as dispatcher
    from squall._tornado import ERROR, READ, WRITE
from squall.coroutine import spawn, ready, _SwitchBack

logger = logging.getLogger(__name__)


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
            logging.exception("Cannot bind socket for socket paremeters:"
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
        logging.error("Cannon bind any sockets for function args: %s"
                      (port, address, family, backlog, flags, reuse_port))
    return sockets


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


def format_address(addr):
    """ Represents address as string.
    """
    result = str(addr)
    if isinstance(addr, (tuple, list)):
        if len(addr) == 2:
            result = "{}:{}".format(*addr)
        if len(addr) == 4:
            result = "[{}]:{}".format(*addr[:2])
    return result


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
                dispatcher.setup_wait_io(self, self._fd, self._mask)
            else:
                dispatcher.disable_watching(self)

    def __call__(self, events):
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
            target, events, payload = done
            target(events, payload)

    async def read_bytes(self, number, *, timeout=None):
        """ Asynchronously reads a number of bytes.
        """
        assert self._active
        assert self._task is None
        assert isinstance(number, int) and number >= 0
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        number = self.buffer_size if number > self.buffer_size else number

        def _check_done(target=None):
            if self._exc is not None:
                exc, self._exc = self._exc, None
                return target, ERROR, exc
            elif len(self._inbuff) >= number:
                data = self._inbuff[:number]
                self._inbuff = self._inbuff[number:]
                return target, READ, data
            return None

        def _read_bytes(target, timeout):
            self.running = READ
            self._task = partial(_check_done, target)
            if timeout > 0:
                dispatcher.setup_wait(target, timeout)

        done = _check_done()
        if done:
            self._task = None
            _, event, payload = done
            if event != ERROR:
                return payload
            else:
                raise payload
        try:
            return await _SwitchBack(_read_bytes, timeout=(timeout or 0))
        except TimeoutError as exc:
            self._task = None
            raise exc

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

        max_bytes = (self.buffer_size
                     if max_bytes is None or max_bytes > self.buffer_size
                     else max_bytes)

        def _check_done(target=None):
            if self._exc is not None:
                exc, self._exc = self._exc, None
                return target, ERROR, exc
            else:
                pos = self._inbuff.find(delimiter)
                if pos >= 0:
                    pos += len(delimiter)
                    data = self._inbuff[:pos]
                    self._inbuff = self._inbuff[pos:]
                    return target, READ, data
                elif len(self._inbuff) >= max_bytes:
                    data = self._inbuff[:max_bytes]
                    self._inbuff = self._inbuff[max_bytes:]
                    return target, READ, data
            return None

        def _read_until(target, timeout):
            self.running = READ
            self._task = partial(_check_done, target)
            if timeout > 0:
                dispatcher.setup_wait(target, timeout)

        done = _check_done()
        if done:
            self._task = None
            _, event, payload = done
            if event != ERROR:
                return payload
            else:
                raise payload
        try:
            return await _SwitchBack(_read_until, timeout=(timeout or 0))
        except TimeoutError as exc:
            self._task = None
            raise exc

    async def write(self, data=None, *, timeout=None, flush=False):
        """ Asynchronously writes outgoing data.
        """
        assert self._active
        assert self._task is None
        assert isinstance(data, bytes) or data is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)

        if data:
            self._outbuff += data
            if (len(self._outbuff) < self.buffer_size / 4 and not flush):
                return

        def _check_done(target=None):
            if self._exc is not None:
                exc, self._exc = self._exc, None
                return target, ERROR, exc
            else:
                if len(self._outbuff) == 0:
                    return target, WRITE, None
            return None

        def _write(target, timeout):
            self.running = WRITE
            self._task = partial(_check_done, target)
            if timeout > 0:
                dispatcher.setup_wait(target, timeout)

        done = _check_done()
        if done:
            self._task = None
            _, event, payload = done
            if event != ERROR:
                return payload
            else:
                raise payload
        try:
            return await _SwitchBack(_write, timeout=(timeout or 0))
        except TimeoutError as exc:
            self._task = None
            raise exc

    def close(self):
        """ Closes stream.
        """
        if self._active:
            self._active = False
            dispatcher.release_watching(self)
            if self._socket:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except IOError:
                    pass
                finally:
                    self._socket.close()


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
        logger.info("Established listener on %s",
                    format_address(listen_socket.getsockname()))

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
            listen_socket.setblocking(0)
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
            logger.info("Finished listener on %s",
                        format_address(listen_socket.getsockname()))
            try:
                listen_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                listen_socket.close()

    async def handle_connection(self, stream, address):
        """ Handles a new incoming connection.
        """

    def listen(self):
        """ Starts connection listening.
        """
        for socket_ in self._sockets:
            self._listeners.append(spawn(self._listener, socket_))

    def close(self):
        """ Closes listener.
        """
        while self._listeners:
            listener = self._listeners.popleft()
            listener.close()
