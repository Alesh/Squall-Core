"""
Low-level event dispatcher and I/O autobuffer designed
for use with a callback functions.
"""
import os
import errno
import signal
from time import time
from tornado.ioloop import IOLoop
from abc import abstractmethod
from squall import abc


class EventDispatcher(abc.EventDispatcher):
    """ Sample event dispatcher.
    """
    TIMEOUT = 0x100
    READ = IOLoop.READ
    WRITE = IOLoop.WRITE
    ERROR = IOLoop.ERROR
    CLEANUP = 0x40000
    SIGNAL = 0x400

    def __init__(self):
        self._cleanup = False
        self._signals = dict()
        self._cancels = dict()
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

    def start(self):
        """ Starts event dispatcher.
        """
        self.watch_signal(lambda revents: self.stop(), signal.SIGINT)
        self._loop.start()

    def stop(self):
        """ Stops event dispatcher.
        """
        def deferred_stop(revents):
            self._cleanup = True
            for callback, cancels in tuple(self._cancels.items()):
                self.cancel(callback)
                if any(cancels):
                    callback(self.CLEANUP)
            self._loop.stop()
            self._loop.close(True)
            self._loop = IOLoop(make_current=False)
            self._cleanup = False

        # deferred stop!
        self.watch_timer(deferred_stop, 0)

    def _del_cancel(self, callback, index):
        if callback in self._cancels:
            self._cancels[callback][index] = None

    def _apply_cancel(self, callback, index):
        if callback in self._cancels:
            if self._cancels[callback][index] is not None:
                self._cancels[callback][index]()
                self._cancels[callback][index] = None

    def _set_cancel(self, callback, index, reset_previous, cancel):
        if callback not in self._cancels:
            self._cancels[callback] = [None, None, None]

        if self._cancels[callback][index] is not None:
            if reset_previous:
                self._cancels[callback][index]()
            else:
                return False
        self._cancels[callback][index] = cancel
        return True

    def watch_timer(self, callback, seconds):
        """ Sets an event dispatcher to call `callback` with code `TIMEOUT`
        after a specified time in seconds.
        """
        def timeout_callback(revents):
            renew = True
            reset_previous = False
            if revents is not None:
                self._del_cancel(callback, 0)
                renew = callback(revents)
            else:
                reset_previous = True
            if renew and not self._cleanup:
                handle = self._loop.add_timeout(
                        time() + seconds, timeout_callback, self.TIMEOUT)
                cancel = lambda: self._loop.remove_timeout(handle)
                if not self._set_cancel(callback, 0, reset_previous, cancel):
                    cancel()

        if seconds >= 0 and not self._cleanup:
            timeout_callback(None)
            return True
        return False

    def watch_io(self, callback, fd, events):
        """ Sets an event dispatcher to call `callback` with code `READ`
        and/or `WRITE` when I/O device  with given `fd` will be ready
        for corresponding I/O operations.
        """
        def io_callback(fd, revents):
            renew = True
            reset_previous = False
            if revents is not None:
                self._apply_cancel(callback, 1)
                renew = callback(revents)

                if callback in self._cancels:
                    if not renew and not any(self._cancels[callback]):
                        self._cancels.pop(callback)
                else:
                    renew = False

            else:
                reset_previous = True
            if renew and not self._cleanup:
                cancel = lambda: self._loop.remove_handler(fd)
                if self._set_cancel(callback, 1, reset_previous, cancel):
                    self._loop.add_handler(fd, io_callback, events)

        if fd >= 0 and events > 0 and not self._cleanup:
            io_callback(fd, None)
            return True
        return False

    def watch_signal(self, callback, signum):
        """ Sets an event dispatcher to call `callback` with code `SIGNAL`
        when a systems signal with given `signum` will be received.
        """
        def signal_callback(revents):
            renew = True
            reset_previous = False
            if revents is not None:
                self._del_cancel(callback, 2)
                renew = callback(revents)
            else:
                reset_previous = True
            if renew and not self._cleanup:
                cancel = lambda: self._cancel_signal(callback, signum)
                if self._set_cancel(callback, 2, reset_previous, cancel):
                    self._watch_signal(callback, signal_callback, signum)

        if signum > 0 and not self._cleanup:
            signal_callback(None)
            return True
        return False

    def cancel(self, callback):
        """ Cancels all watchings for a given `callback`.
        """
        if callback in self._cancels:
            for cancel in self._cancels.pop(callback):
                if cancel is not None:
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
        self._events = self._disp.READ

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
        if revents & self._disp.ERROR:
            self._errno = errno.EIO
        else:
            try:
                if revents & self._disp.READ:
                    block = self._read_block(self._block_size)
                    if len(block) > 0:
                        self._inbuf += block
                        if len(self._inbuf) >= self._max_size:
                            self._events = self._events ^ self._disp.READ
                    else:
                        self._events = self._events ^ self._disp.READ
                        self._errno = errno.ECONNRESET
                if revents & self._disp.WRITE:
                    block = self._outbuf[:self._block_size]
                    if len(block) > 0:
                        sent = self._write_block(block)
                        self._outbuf = self._outbuf[sent:]
                    if len(self._outbuf) == 0:
                        self._events = self._events ^ self._disp.WRITE
            except IOError as exc:
                self._errno = exc.errno
        callback, revents, result = self._check_task()
        if result is not None:
            callback(revents, result)
        return not self._closed

    def _check_task(self):
        if self._task:
            callback, event, *args = self._task
            if event == self._disp.READ:
                num_bytes = args[0]
                if len(args) == 2:
                    delimiter = args[1]
                    pos = self._inbuf.find(delimiter)
                    if pos >= 0:
                        pos += len(delimiter)
                        result, self._inbuf = (self._inbuf[:pos],
                                               self._inbuf[pos:])
                        self._events = self._events | self._disp.READ
                        self.cancel()
                        return callback, event, result
                if num_bytes <= len(self._inbuf):
                    result, self._inbuf = (self._inbuf[:num_bytes],
                                           self._inbuf[num_bytes:])
                    self._events = self._events | self._disp.READ
                    self.cancel()
                    return callback, event, result
            elif event == self._disp.WRITE:
                if len(self._outbuf) == 0:
                    self.cancel()
                    return callback, event, True
            if self._errno != 0:
                result = self._errno
                self._errno = 0
                self.cancel()
                return callback, self._disp.ERROR, result
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
            self._task = (callback, self._disp.READ, number)
            _, _, result = self._check_task()
            if result is not None:
                self._disp.watch_timer(
                    lambda *args: callback(self._disp.READ, result), 0)
            return True
        return False

    def watch_read_until(self, callback, delimiter, max_number):
        """ Sets an autobuffer to call `callback` with code `READ`
        and result as block of bytes when autobuffer received given
        `delimiter` or `number` of bytes, `delimiter` would be
        included in result.
        """
        if not self._closed and not self._errno:
            self._task = (callback, self._disp.READ, max_number, delimiter)
            _, _, result = self._check_task()
            if result is not None:
                self._disp.watch_timer(
                    lambda *args: callback(self._disp.READ, result), 0)
            return True
        return False

    def watch_flush(self, callback):
        """ Sets an autobuffer to call `callback` with code `WRITE`
        when a autobuffer will complete drain outcoming buffer.
        """
        if not self._closed and not self._errno:
            self._task = (callback, self._disp.WRITE)
            _, _, result = self._check_task()
            if result is not None:
                self._disp.watch_timer(
                    lambda *args: callback(self._disp.READ, result), 0)
            return True
        return False

    def write(self, data):
        """ Puts `data` bytes to outcoming buffer to asynchronous
        sending. Returns the number of bytes written.
        """
        self._events = self._events | self._disp.WRITE
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
