import os
import errno
import logging
import asyncio
from functools import partial
from .buffers import OutcomingBuffer, IncomingBuffer
from .buffers import READ, WRITE, TIMEOUT, SIGNAL, ERROR, CLEANUP, BUFFER


class CannotSetupWatching(RuntimeError):
    def __init__(self, msg=None):
        super().__init__(msg or "Cannot setup an event watching")


class EventLoop(object):
    """ Event loop implementation on the asyncio event loops
    """
    def __init__(self):
        self._fds = dict()
        self._signals = dict()
        self._running = False
        self._loop = asyncio.get_event_loop()

    def _handle_signal(self, signum):
        for callback in tuple(self._signals[signum]):
            self._loop.call_soon(callback, True)

    @property
    def running(self):
        """ Returns `True` if tis is active.
        """
        return self._running

    def start(self):
        """ Starts the event dispatching.
        """
        logging.info("Using asyncio based callback classes")
        self._running = True
        self._loop.run_forever()
        self._running = False

    def stop(self):
        """ Stops the event dispatching.
        """
        self._loop.stop()

    def setup_io(self, callback, fd, events):
        """ Setup to run the `callback` when I/O device with
        given `fd` would be ready to read or/and write.
        Returns handle for using with `EventLoop.update_io` and `EventLoop.cancel_io`
        """
        if events & (READ | WRITE):
            if events & READ:
                self._loop.add_reader(fd, callback, READ)
            if events & WRITE:
                self._loop.add_writer(fd, callback, WRITE)
            self._fds[fd] = [callback, events]
            return fd
        raise CannotSetupWatching()

    def update_io(self, handle, events):
        """ Updates call settings for callback which was setup with `EventLoop.setup_io`.
        """
        fd = handle
        if fd in self._fds:
            callback, _events = self._fds[fd]
            if _events != events:
                if (events & READ) and not _events & READ:
                    self._loop.add_reader(fd, callback, READ)
                elif (_events & READ) and not events & READ:
                    self._loop.remove_reader(fd)
                if (events & WRITE) and not _events & WRITE:
                    self._loop.add_writer(fd, callback, WRITE)
                elif (_events & WRITE) and not events & WRITE:
                    self._loop.remove_writer(fd)
                self._fds[fd][1] = events
                return True
        return False

    def cancel_io(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_io`.
        """
        fd = handle
        if fd in self._fds:
            _, events = self._fds.pop(fd)
            if events & READ:
                self._loop.remove_reader(fd)
            if events & WRITE:
                self._loop.remove_writer(fd)
            return True
        return False

    def setup_timer(self, callback, seconds):
        """ Setup to run the `callback` after a given `seconds` elapsed.
        Returns handle for using with `EventLoop.cancel_timer`
        """
        deadline = self._loop.time() + seconds
        exc = TimeoutError("Timed out")
        handle = self._loop.call_at(deadline, callback, exc)
        if handle is not None:
            return handle
        raise CannotSetupWatching()

    def cancel_timer(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_timer`.
        """
        if isinstance(handle, asyncio.Handle):
            handle.cancel()
            return True
        return False

    def setup_signal(self, callback, signum):
        """ Setup to run the `callback` when system signal with a given `signum` received.
        Returns handle for using with `EventLoop.cancel_signal`
        """
        if signum not in self._signals:
            self._loop.add_signal_handler(signum, self._handle_signal, signum)
            self._signals[signum] = list()
        self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_signal`.
        """
        signum, callback = handle
        if signum in self._signals:
            self._signals[signum].remove(callback)
            return True
        return False


class EventBuffer(object):
    """ Base event-driven I/O stream buffer
    """

    def __init__(self, loop, fd, block_size=0, buffer_size=0):
        self._fd = fd
        self._loop = loop
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._mode = self._handle = None
        self._adjust_buffer_size()
        self._in = IncomingBuffer(self._receive_block, self._receiving,
                                  self._block_size, self._buffer_size)
        self._out = OutcomingBuffer(self._transmit_block, self._transmiting,
                                    self._block_size, self._buffer_size)
        self._receiving(True)

    @property
    def fd(self):
        """ File descriptor """
        return self._fd

    @property
    def active(self):
        """ Return `True` if active """
        return self._fd >= 0

    @property
    def mode(self):
        """ Current watching mode """
        return self._mode or 0

    @property
    def block_size(self):
        """ Buffer block size """
        return self._block_size

    @property
    def buffer_size(self):
        """ Maximum buffer size """
        return self._buffer_size

    @property
    def incoming_size(self):
        """ Incomming buffer size """
        return self._in.size

    @property
    def outcoming_size(self):
        """ Outcomming buffer size """
        return self._out.size

    def setup_read_until(self, callback, delimiter, max_number=None):
        """ Sets up buffer to read until delimiter found.
        """
        if self.active:
            callback = partial(self._read_callback, callback)
            result = self._in.setup(callback, delimiter, max_number or self._buffer_size)
            if result > 0:
                return self.read(result)
            elif result < 0:
                raise LookupError("`delimiter` not found but `max_number`")
            return None
        raise CannotSetupWatching()

    def setup_read_exactly(self, callback, number):
        """ Sets up buffer to read exactly number of bytes
        """
        if self.active:
            callback = partial(self._read_callback, callback)
            result = self._in.setup(callback, None, number)
            if result > 0:
                return self.read(result)
            return None
        raise CannotSetupWatching()

    def cancel_read(self):
        """ Cancels callback which was setup with `EventBuffer.setup_read_*`.
        """
        self._in.cancel()

    def read(self, number):
        """ Read bytes from incoming buffer how much is there, but not more `number`.
        """
        if self.active:
            result = self._in.read(number)
            if result:
                self._receiving(True)
                return result
        return b''

    def setup_flush(self, callback):
        """ Setup to run the `callback` when buffer would be flushed.
        """
        if self.active:
            callback = partial(self._write_callback, callback)
            if self._out.setup(callback, 0) > 0:
                return True
            return None
        raise CannotSetupWatching()

    def cancel_flush(self):
        """ Cancels callback which was setup with `EventBuffer.setup_flush`.
        """
        self._out.cancel()

    def write(self, data):
        """ Writes data to the outcoming buffer.
        """
        if self.active:
            result = self._out.write(data)
            if result:
                self._transmiting(True)
                return result
        return 0

    def release(self):
        """ Deactivate and cleanups buffer. """
        self._set_mode(0)
        self._in.cleanup()
        self._out.cleanup()
        self._loop = None
        self._fd = -1

    def _set_mode(self, value):
        if self.active and value != self.mode:
            if self._handle is None:
                self._handle = self._loop.setup_io(self._event_handler, self._fd, value)
                if self._handle is not None:
                    self._mode = value
            else:
                if value > 0:
                    if self._loop.update_io(self._handle, value):
                        self._mode = value
                else:
                    if self._loop.cancel_io(self._handle):
                        self._mode = self._handle = None

    def _adjust_buffer_size(self):
        self._block_size = self._block_size if self._block_size > 1024 else 1024
        self._block_size += 1024 if (self._block_size % 1024) else 0
        self._block_size = int(self._block_size / 1024) * 1024
        self._buffer_size = self._buffer_size if self._buffer_size > 1024 * 4 else 1024 * 4
        self._buffer_size = int(self._buffer_size / self._block_size) * self._block_size

    def _receiving(self, turn):
        if turn and not self.mode & READ:
            self._set_mode(self.mode | READ)
        elif self.mode & READ and not turn:
            self._set_mode(self.mode ^ READ)
        return self.mode & READ

    def _transmiting(self, turn):
        """"""
        if turn and not self.mode & WRITE:
            self._set_mode(self.mode | WRITE)
        elif self.mode & WRITE and not turn:
            self._set_mode(self.mode ^ WRITE)
        return self.mode & WRITE

    def _read_callback(self, callback, revents, payload=None):
        if revents & ERROR:
            if revents & BUFFER:
                if revents & READ:
                    callback(LookupError("`delimiter` not found but `max_number`"))
                else:
                    if payload:
                        exc = IOError(payload, os.strerror(payload))
                    else:
                        exc = self._reset_exception()
                    callback(exc)
            else:
                callback(IOError("Internal event loop error"))
        elif revents == (READ | BUFFER):
            callback(self.read(payload))

    def _write_callback(self, callback, revents, payload=None):
        if revents & ERROR:
            if revents & BUFFER:
                if payload:
                    exc = IOError(payload, os.strerror(payload))
                else:
                    exc = self._reset_exception()
                callback(exc)
            else:
                callback(IOError("Internal event loop error"))
        elif revents == (WRITE | BUFFER):
            callback(True)

    def _event_handler(self, revents):
        self._in(revents)
        self._out(revents)

    def _receive_block(self, number):
        raise NotImplementedError("Metod `_receive_block` must be implemented")
        # return data, errno

    def _transmit_block(self, block):
        raise NotImplementedError("Metod `_transmit_block` must be implemented")
        # return sent, errno

    def _reset_exception(self):
        raise NotImplementedError("Metod `_reset_exception` must be implemented")
        # return instance of reset exception


class SocketBuffer(EventBuffer):
    """ Socket auto buffer
    """

    def __init__(self, loop, socket_, block_size, buffer_size):
        self._socket = socket_
        self._socket.setblocking(0)
        super().__init__(loop, socket_.fileno(), block_size, buffer_size)

    def _receive_block(self, size):
        try:
            block = self._socket.recv(size)
            return block, 0
        except IOError as exc:
            return b'', exc.errno or errno.EIO

    def _transmit_block(self, block):
        try:
            sent = self._socket.send(block)
            return sent, 0
        except IOError as exc:
            return 0, exc.errno or errno.EIO

    def _reset_exception(self):
        return IOError(errno.ECONNRESET, os.strerror(errno.ECONNRESET))


class FileBuffer(EventBuffer):
    """ File auto buffer
    """

    def _receive_block(self, size):
        try:
            block = os.read(self.fd, size)
            return block, 0
        except IOError as exc:
            return b'', exc.errno or errno.EIO

    def _transmit_block(self, block):
        try:
            sent = os.write(self.fd, block)
            return sent, 0
        except IOError as exc:
            return 0, exc.errno or errno.EIO

    def _reset_exception(self):
        return EOFError("End of file")
