"""
Low-level classes
"""
import os
import errno
import signal
import threading
from time import time
from functools import partial
from tornado.ioloop import IOLoop
from abc import abstractmethod
from squall import abc


class EventLoop(abc.EventLoop):
    """ Sample event loop.
    """
    TIMEOUT = 0x100
    READ = IOLoop.READ
    WRITE = IOLoop.WRITE
    ERROR = IOLoop.ERROR
    CLEANUP = 0x40000
    SIGNAL = 0x400

    _tls = threading.local()

    def __init__(self):
        self._running = False
        self._finishing = False
        self._pending = dict()
        self._signals = dict()
        self._loop = IOLoop(make_current=False)

    def _handle_signal(self, signum, frame):
        for callback in tuple(self._signals[signum].values()):
            self._loop.add_callback_from_signal(callback, self.SIGNAL)

    def _watch_signal(self, ctx, callback, signum):
        if signum not in self._signals:
            signal.signal(signum, self._handle_signal)
            self._signals[signum] = dict()
        self._signals[signum][ctx] = callback

    def _cancel_signal(self, ctx, signum):
        if signum in self._signals:
            self._signals[signum].pop(ctx, None)

    @classmethod
    def instance(cls):
        """ Returns thread local instance.
        """
        if not hasattr(cls._tls, 'instance'):
            setattr(cls._tls, 'instance', cls())
        return getattr(cls._tls, 'instance')

    @property
    def running(self):
        """ Returns `True` if event loop is running.
        """
        return self._running

    @property
    def pending(self):
        """ Number of the pending watchers.
        """
        return len(self._pending)

    def start(self):
        """ Starts event loop.
        """
        self._running = True
        self._loop.start()

    def stop(self):
        """ Stops event loop.
        """
        if not self._finishing:
            self._finishing = True
            while len(self._pending):
                (callback, ctx, _), cancel = self._pending.popitem()
                cancel()
                callback(self.CLEANUP)
            self._loop.stop()
            self._loop.close(True)
            delattr(self.__class__._tls, 'instance')
            self._running = False

    def watch_timer(self, callback, ctx, seconds):
        """ Sets an event dispatcher to call `callback` for `ctx`
        with code `TIMEOUT` after a specified time in seconds.
        If success returns callable which cancels this watching
        at call otherwise `None`.
        """
        timeout = list()
        key = (callback, ctx, 0)

        def cancel_():
            self._pending.pop(key)
            self._loop.remove_timeout(timeout.pop())

        def callback_(revents):
            timeout.append(self._loop.add_timeout(time() + seconds,
                                                  callback_, self.TIMEOUT))
            self._pending[key] = cancel_
            if revents is not None:
                callback(ctx, revents)

        if not self._finishing:
            cancel = self._pending.get(key)
            if cancel is not None:
                cancel()
            callback_(None)
        return self._pending[key]

    def watch_io(self, callback, ctx, fd, events):
        """ Sets an event dispatcher to call `callback` for `ctx` 
        with code `READ` and/or `WRITE` when I/O device  with given
        `fd` will be ready for corresponding I/O operations.
        If success returns callable which cancels this watching
        at call otherwise `None`.
        """
        key = (callback, ctx, 1)

        def cancel_():
            self._pending.pop(key)
            self._loop.remove_handler(fd)

        def callback_(fd, revents):
            callback(ctx, revents)

        if not self._finishing:
            cancel = self._pending.get(key)
            if cancel is not None:
                cancel()
            self._loop.add_handler(fd, callback_, events)
            self._pending[key] = cancel_
        return self._pending[key]

    def watch_signal(self, callback, ctx, signum):
        """ Sets an event dispatcher to call `callback` for `ctx`  
        with code `SIGNAL` when a systems signal with given `signum`
        will be received.
        If success returns callable which cancels this watching
        at call otherwise `None`.
        """
        key = (callback, ctx, 2)

        def cancel_():
            self._pending.pop(key)
            self._cancel_signal(callback, signum)

        def callback_(revents):
            self._watch_signal(callback, callback_, signum)
            self._pending[key] = cancel_
            if revents is not None:
                callback(ctx, revents)

        if not self._finishing:
            cancel = self._pending.get(key)
            if cancel is not None:
                cancel()
            callback_(None)
        return self._pending[key]


READ = EventLoop.READ
WRITE = EventLoop.WRITE
ERROR = EventLoop.ERROR
SIGNAL = EventLoop.SIGNAL
TIMEOUT = EventLoop.TIMEOUT
CLEANUP = EventLoop.CLEANUP


class EventDispatcher(object):
    """ Sample event dispatcher.
    """

    def __init__(self):
        self.__loop = None
        self._finishing = False
        self._cancels = dict()

    @property
    def _loop(self):
        if self.__loop is None:
            self.__loop = EventLoop.instance()
        return self.__loop

    def _callback(self, callback, revents):
        if not callback(revents):
            self.cancel(callback)

    @property
    def initialized(self):
        """ Returns `True` if event dispatcher binded with event loop.
        """
        return self.__loop is not None

    def start(self):
        """ Starts event dispatcher.
        """
        if not self._loop.running:
            self._loop.start()

    def stop(self):
        """ Stops event dispatcher.
        """
        def deferred_stop(_):
            while len(self._cancels):
                callback, cancels = self._cancels.popitem()
                for cancel in cancels.values():
                    cancel()
                callback(self._loop.CLEANUP)
            if not self._loop.pending:
                self._loop.stop()

        if not self._finishing:
            self.watch_timer(deferred_stop, 0)
            self._finishing = True

    def watch_timer(self, callback, seconds):
        """ Sets an event dispatcher to call `callback` with code `TIMEOUT`
        after a specified time in seconds.
        """
        if not self._finishing:
            cancel = self._loop.watch_timer(self._callback, callback, seconds)
            if cancel is not None:
                if callback not in self._cancels:
                    self._cancels[callback] = dict()
                self._cancels[callback][0] = cancel
                return True
        return False

    def watch_io(self, callback, fd, events):
        """ Sets an event dispatcher to call `callback` with code `READ`
        and/or `WRITE` when I/O device  with given `fd` will be ready
        for corresponding I/O operations.
        """
        if not self._finishing:
            cancel = self._loop.watch_io(self._callback, callback, fd, events)
            if cancel is not None:
                if callback not in self._cancels:
                    self._cancels[callback] = dict()
                self._cancels[callback][1] = cancel
                return True
        return False

    def watch_signal(self, callback, signum):
        """ Sets an event dispatcher to call `callback` with code `SIGNAL`
        when a systems signal with given `signum` will be received.
        """
        if not self._finishing:
            cancel = self._loop.watch_signal(self._callback, callback, signum)
            if cancel is not None:
                if callback not in self._cancels:
                    self._cancels[callback] = dict()
                self._cancels[callback][2] = cancel
                return True
        return False

    def cancel(self, callback):
        """ Cancels all watchings for a given `callback`.
        """
        cancels = self._cancels.pop(callback, None)
        if cancels is not None:
            for cancel in cancels.values():
                cancel()


class AutoBuffer(abc.AutoBuffer):
    """ Sample autobuffer
    """
    def __init__(self, disp, fileno, block_size,  max_size):
        self._errno = 0
        self._inbuf = b''
        self._outbuf = b''
        self._task = None
        self.__events = 0
        self._closed = False
        assert isinstance(disp, abc.EventDispatcher)
        self._disp = disp
        self._fileno = fileno
        self._block_size = (int(block_size / 64) * 64
                            if block_size > 256 else 256)
        self._max_size = (int(max_size / self.block_size) * self.block_size
                          if max_size > self.block_size * 8
                          else self.block_size * 8)
        self._events = READ

    @property
    def _events(self):
        return self.__events

    @_events.setter
    def _events(self, value):
        value = value or 0
        if value != self.__events and not self._closed:
            if value:
                if self._disp.watch_io(self._handler, self._fileno, value):
                    self.__events = value
                else:
                    self._errno = errno.ECANCELED
            else:
                self._disp.cancel(self._handler)
                self.__events = value

    def _handler(self, revents):
        if revents & ERROR:
            self._errno = errno.EIO
        else:
            try:
                if revents & READ:
                    block = self._read_block(self._block_size)
                    if len(block) > 0:
                        self._inbuf += block
                        if len(self._inbuf) >= self._max_size:
                            self._events = self._events ^ READ
                    else:
                        self._events = self._events ^ READ
                        self._errno = errno.ECONNRESET
                if revents & WRITE:
                    block = self._outbuf[:self._block_size]
                    if len(block) > 0:
                        sent = self._write_block(block)
                        self._outbuf = self._outbuf[sent:]
                    if len(self._outbuf) == 0:
                        self._events = self._events ^ WRITE
            except IOError as exc:
                self._errno = exc.errno
        callback, revents, result = self._check_task()
        if result is not None:
            callback(revents, result)
        return not self._closed

    def _check_task(self):
        if self._task:
            callback, event, *args = self._task
            if event == READ:
                num_bytes = args[0]
                if len(args) == 2:
                    delimiter = args[1]
                    pos = self._inbuf.find(delimiter)
                    if pos >= 0:
                        pos += len(delimiter)
                        result, self._inbuf = (self._inbuf[:pos],
                                               self._inbuf[pos:])
                        self._events = self._events | READ
                        self.cancel()
                        return callback, event, result
                if num_bytes <= len(self._inbuf):
                    result, self._inbuf = (self._inbuf[:num_bytes],
                                           self._inbuf[num_bytes:])
                    self._events = self._events | READ
                    self.cancel()
                    return callback, event, result
            elif event == WRITE:
                if len(self._outbuf) == 0:
                    self.cancel()
                    return callback, event, True
            if self._errno != 0:
                result = self._errno
                self._errno = 0
                self.cancel()
                return callback, ERROR, result
        return (None, None, None)

    @abstractmethod
    def _read_block(self, size):
        """Should be read and return a given numbers of bytes
        from I/O device.
        """

    @abstractmethod
    def _write_block(self, block):
        """Should be try write a block of bytes to device and
        return number of writen bytes."""

    @property
    def block_size(self):
        """ The block size of data reads / writes to the I/O device at once.
        must be int(block_size / 64) == block_size / 64
        and strongly recommended block_size <= 64 * 1024
        """
        return self._block_size

    @property
    def max_size(self):
        """ Maximum size of the incoming / outcoming data buffers.
        must be int(max_size / block_size) == max_size / block_size
        """
        return self._max_size

    @property
    def last_error(self):
        """ Returns last occurred error.
        """
        if self._errno:
            exc = IOError(self._errno, os.strerror(self._errno))
            self._errno = 0
            return exc
        else:
            return None

    @property
    def closed(self):
        """ Returns `True` if this is released.
        """
        return self._closed

    def watch_read_bytes(self, callback, number):
        """ Sets an autobuffer to call `callback` with code `READ`
        and result as block of bytes when autobuffer received given
        `number` of bytes.
        """
        if not self._closed and not self._errno:
            self._task = (callback, READ, number)
            _, _, result = self._check_task()
            if result is not None:
                self._disp.watch_timer(
                    lambda *args: callback(READ, result), 0)
            return True
        return False

    def watch_read_until(self, callback, delimiter, max_number):
        """ Sets an autobuffer to call `callback` with code `READ`
        and result as block of bytes when autobuffer received given
        `delimiter` or `number` of bytes, `delimiter` would be
        included in result.
        """
        if not self._closed and not self._errno:
            self._task = (callback, READ, max_number, delimiter)
            _, _, result = self._check_task()
            if result is not None:
                self._disp.watch_timer(
                    lambda *args: callback(READ, result), 0)
            return True
        return False

    def watch_flush(self, callback):
        """ Sets an autobuffer to call `callback` with code `WRITE`
        when a autobuffer will complete drain outcoming buffer.
        """
        if not self._closed and not self._errno:
            self._task = (callback, WRITE)
            _, _, result = self._check_task()
            if result is not None:
                self._disp.watch_timer(
                    lambda *args: callback(READ, result), 0)
            return True
        return False

    def write(self, data):
        """ Puts `data` bytes to outcoming buffer to asynchronous
        sending. Returns the number of bytes written.
        """
        self._events = self._events | WRITE
        if not self._closed and not self._errno:
            chunk = data[:self._max_size - len(self._outbuf)]
            self._outbuf += chunk
            return len(chunk)
        else:
            return 0

    def cancel(self):
        """ Cancels all watchings.
        """
        self._task = None

    def release(self):
        """ Cancels all watchings and destroys internal buffers.
        """
        self._events = None
        self._closed = True
        self._outbuf = b''
        self._inbuf = b''


class SocketAutoBuffer(AutoBuffer):
    """ Sample socket autobuffer
    """
    def __init__(self, disp, sock, block_size=1024,  max_size=16384):
        self._sock = sock
        super(SocketAutoBuffer, self).__init__(disp, sock.fileno(),
                                               block_size,  max_size)

    def _read_block(self, size):
        """Should be read and return a given numbers of bytes
        from I/O device.
        """
        return self._sock.recv(size)

    def _write_block(self, block):
        """Should be try write a block of bytes to device and
        return number of writen bytes."""
        return self._sock.send(block)
