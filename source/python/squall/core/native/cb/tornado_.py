""" Module of callback classes based on tornado
"""
import logging
import signal
from socket import SocketType, SHUT_RDWR
from time import time

from squall.core.native.cb.abc import AutoBuffer as AbcAutoBuffer
from squall.core.native.cb.abc import EventLoop as AbcEventLoop
from squall.core.native.cb.abc import SocketAcceptor as AbcSocketAcceptor
from tornado.ioloop import IOLoop
from tornado.netutil import add_accept_handler, bind_sockets as tornado_bind_sockets


class EventLoop(AbcEventLoop):
    """ tornado based implementation of `squall.core.native.cb.abc.EventLoop`
    """

    READ = IOLoop.READ
    WRITE = IOLoop.WRITE

    def __init__(self):
        self._signals = dict()
        self._loop = IOLoop(make_current=False)
        super().__init__()

    def start(self):
        """ See more: `AbcEventLoop.start` """
        logging.info("Using tornado based callback classes")
        self._loop.start()

    def stop(self):
        """ See more: `AbcEventLoop.stop` """
        self._loop.stop()

    def setup_timeout(self, callback, seconds, result=True):
        """ See more: `AbcEventLoop.setup_timeout` """
        deadline = time() + seconds
        return self._loop.add_timeout(deadline, callback, result)

    def cancel_timeout(self, handle):
        """ See more: `AbcEventLoop.setup_timeout` """
        self._loop.remove_timeout(handle)

    def setup_ready(self, callback, fd, events):
        """ See more: `AbcEventLoop.setup_ready` """

        def handler(_, revents):
            if events & IOLoop.ERROR:
                callback(IOError("Internal eventloop error"))
            else:
                callback(revents)

        self._loop.add_handler(fd, handler, events)
        return fd

    def cancel_ready(self, handle):
        """ See more: `AbcEventLoop.cancel_ready` """
        self._loop.remove_handler(handle)

    def _handle_signal(self, signum, _):
        for callback in tuple(self._signals[signum]):
            self._loop.add_callback_from_signal(callback, signum)

    def setup_signal(self, callback, signum):
        """ See more: `AbcEventLoop.setup_signal` """
        if signum not in self._signals:
            signal.signal(signum, self._handle_signal)
            self._signals[signum] = list()
        if callback not in self._signals[signum]:
            self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handler):
        """ See more: `AbcEventLoop.cancel_signal` """
        signum, callback = handler
        if signum in self._signals:
            self._signals[signum].remove(callback)


class SocketAutoBuffer(AbcAutoBuffer):
    """ tornado based implementation of `squall.core.native.cb.abc.AutoBuffer` for socket
    """
    READ = IOLoop.READ
    WRITE = IOLoop.WRITE

    def __init__(self, event_loop: EventLoop, socket_: SocketType, block_size, buffer_size):
        self._in = b''
        self._out = b''
        self._task = None
        self._mode = self.READ
        self._socket = socket_
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._loop = event_loop._loop
        self._loop.add_handler(self._socket.fileno(),
                               lambda _, revents: self._event_handler(revents), self._mode)

    def _event_handler(self, revents):
        last_error = None
        mode = self._mode
        if isinstance(revents, Exception):
            last_error = revents
        else:
            try:
                if revents & self.READ:
                    max_size = self._buffer_size - len(self._in)
                    block_size = self._block_size if self._block_size < max_size else max_size
                    block = self._socket.recv(block_size)
                    if len(block) > 0:
                        self._in += block
                        if len(self._in) >= self._buffer_size:
                            mode ^= self.READ
                    else:
                        mode ^= self.READ
                        raise ConnectionResetError("Connection reset by peer")
                if revents & self.WRITE:
                    block = self._out[:self._block_size]
                    if len(block) > 0:
                        sent_size = self._socket.send(block)
                        self._out = self._out[sent_size:]
                    if len(self._out) == 0:
                        mode ^= self.WRITE
            except IOError as exc:
                last_error = exc

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
                    result = method(len(self._out))
            if result is not None:
                self.cancel_task()
                callback(result)

        if self.active:
            # recalc I/O mode
            if not (mode & self.READ):
                if len(self._in) < self._buffer_size:
                    mode |= self.READ
            if not (mode & self.WRITE):
                if len(self._out) > 0:
                    mode |= self.WRITE
            if mode != self._mode:
                self._mode = mode
                self._loop.update_handler(self._socket.fileno(), self._mode)

    @property
    def active(self):
        """ See more: `AbcAutoBuffer.active` """
        return self._socket is not None

    @property
    def block_size(self):
        """ See more: `AbcAutoBuffer.block_size` """
        return self._block_size

    @property
    def buffer_size(self):
        """ See more: `AbcAutoBuffer.buffer_size` """
        return self._buffer_size

    def setup_task(self, callback, trigger_event, task_method, timeout):
        """ See more: `AbcAutoBuffer.setup_task` """
        result = None
        exec_timeout = TimeoutError("I/O timeout")
        if timeout < 0:
            result = exec_timeout
        elif trigger_event == self.READ:
            result = task_method(self._in)
        elif trigger_event == self.WRITE:
            result = task_method(len(self._out))
        if result is None:
            if timeout > 0:
                deadline = time() + timeout
                timeout = self._loop.add_timeout(deadline, self._event_handler, exec_timeout)
            else:
                timeout = None
            self._task = (callback, trigger_event, task_method, timeout)
        return result

    def cancel_task(self):
        """ See more: `AbcAutoBuffer.cancel_task` """
        if self._task is not None:
            callback, trigger_event, task_method, timeout = self._task
            if timeout is not None:
                self._loop.remove_timeout(timeout)
            self._task = None

    def read(self, max_bytes):
        """ See more: `AbcAutoBuffer.read` """
        result, self._in = self._in[:max_bytes], self._in[max_bytes:]
        return result

    def write(self, data):
        """ See more: `AbcAutoBuffer.write` """
        block = b''
        if self.active:
            block = data[:self._buffer_size - len(self._out)]
            self._out += block
            if not (self._mode & self.WRITE):
                self._mode |= self.WRITE
                self._loop.update_handler(self._socket.fileno(), self._mode)
        return len(block)

    def close(self):
        """ See more: `AbcAutoBuffer.close` """
        try:
            self.cancel_task()
            self._loop.remove_handler(self._socket.fileno())
            self._socket.shutdown(SHUT_RDWR)
        except:
            pass
        finally:
            self._socket.close()
            self._socket = None


class SocketAcceptor(AbcSocketAcceptor):
    """ tornado based implementation of `squall.core.native.cb.abc.SocketAcceptor` for socket
    """

    def __init__(self, event_loop, socket_, on_accept):
        self._fd = socket_.fileno()
        self._loop = event_loop._loop
        add_accept_handler(socket_, on_accept, self._loop)

    def close(self):
        """ See more `AbcSocketAcceptor.close` """
        self._loop.remove_handler(self._fd)


def bind_sockets(port, address, *, backlog=127, reuse_port=False):
    return tornado_bind_sockets(port, address, backlog=backlog, reuse_port=reuse_port)
