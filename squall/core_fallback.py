""" Squall fallback core module
"""
import errno
import asyncio
import logging
from socket import SHUT_RDWR
from abc import ABCMeta, abstractmethod


class EventLoop(object):
    """ Event loop implementation on the asyncio event loops
    """
    READ    = 0x00000001
    WRITE   = 0x00000002
    TIMEOUT = 0x00000004
    SIGNAL  = 0x00000008
    ERROR   = 0x00000016

    def __init__(self):
        self._fds = dict()
        self._signals = dict()
        self._running = False
        self._loop = asyncio.get_event_loop()

    def _handle_signal(self, signum):
        for callback in tuple(self._signals[signum]):
            self._loop.call_soon(callback, self.SIGNAL)

    def is_running(self):
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
        if events & (self.READ | self.WRITE):
            if events & self.READ:
                self._loop.add_reader(fd, callback, self.READ)
            if events & self.WRITE:
                self._loop.add_writer(fd, callback, self.WRITE)
            self._fds[fd] = [callback, events]
            return fd
        return None

    def setup_timer(self, callback, seconds):
        """ Setup to run the `callback` after a given `seconds` elapsed.
        Returns handle for using with `EventLoop.cancel_timer`
        """
        deadline = self._loop.time() + seconds
        return self._loop.call_at(deadline, callback, self.TIMEOUT)

    def setup_signal(self, callback, signum):
        """ Setup to run the `callback` when system signal with a given `signum` received.
        Returns handle for using with `EventLoop.cancel_signal`
        """
        if signum not in self._signals:
            self._loop.add_signal_handler(signum, self._handle_signal, signum)
            self._signals[signum] = list()
        self._signals[signum].append(callback)
        return signum, callback

    def update_io(self, handle, events):
        """ Updates call settings for callback which was setup with `EventLoop.setup_io`.
        """
        fd = handle
        if fd in self._fds:
            callback, _events = self._fds[fd]
            if _events != events:
                if (events & self.READ) and not (_events & self.READ):
                    self._loop.add_reader(fd, callback, self.READ)
                elif (_events & self.READ) and not (events & self.READ):
                    self._loop.remove_reader(fd)
                if (events & self.WRITE) and not (_events & self.WRITE):
                    self._loop.add_writer(fd, callback, self.WRITE)
                elif (_events & self.WRITE) and not (events & self.WRITE):
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
            if events & self.READ:
                self._loop.remove_reader(fd)
            if events & self.WRITE:
                self._loop.remove_writer(fd)
            return True
        return False

    def cancel_timer(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_timer`.
        """
        try:
            handle.cancel()
            return True
        except Exception:
            return False

    def cancel_signal(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_signal`.
        """
        signum, callback = handle
        if signum in self._signals:
            self._signals[signum].remove(callback)
            return True
        return False


class AutoBuffer(metaclass=ABCMeta):
    """ Abstract base I/O auto buffer
    """

    def __init__(self, event_loop, fd, block_size, buffer_size):
        self._in = b''
        self._out = b''
        self._task = None
        self._loop = event_loop
        self._mode = self.READ
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._handle = self._loop.setup_io(self._event_handler, fd, self._mode)

    @property
    def active(self):
        """ Returns `True` if this is active (not closed). """
        return self._handle is not None

    @property
    def READ(self):
        """ Event code "I/O device ready to read". """
        return self._loop.READ

    @property
    def WRITE(self):
        """ Event code "I/O device ready to write". """
        return self._loop.WRITE

    @property
    def ERROR(self):
        """ Event code "I/O error". """
        return self._loop.ERROR

    @property
    def block_size(self):
        """ Size of block of data reads/writes to the I/O device at once. """
        return self._block_size

    @property
    def buffer_size(self):
        """ Maximum size of the read/write buffers. """
        return self._buffer_size

    def _event_handler(self, revents):
        last_error = errno.EIO if revents & self.ERROR else None
        mode = self._mode

        if revents & (self.READ | self.WRITE) == revents:
            try:
                if revents & self.READ:
                    max_size = self._buffer_size - len(self._in)
                    block_size = self._block_size if self._block_size < max_size else max_size
                    block = self._read_block(block_size)
                    if len(block) > 0:
                        self._in += block
                        if len(self._in) >= self._buffer_size:
                            mode ^= self.READ
                    else:
                        mode ^= self.READ
                        last_error = errno.ECONNRESET
                if revents & self.WRITE:
                    block = self._out[:self._block_size]
                    if len(block) > 0:
                        sent_size = self._write_block(block)
                        self._out = self._out[sent_size:]
                    if len(self._out) == 0:
                        mode ^= self.WRITE
            except IOError as exc:
                last_error = exc.errno or errno.EIO

        if self._task is not None:
            result = None
            # apply buffer task
            callback, event, method, *args = self._task
            if event & revents:
                result, payload = method(*args)
            if not result and last_error is not None:
                result = self.ERROR
                payload = last_error
            if result:
                self.cancel_task()
                callback(result, payload)

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
                self._loop.update_io(self._handle, self._mode)

    @abstractmethod
    def _read_block(self, size: int) -> bytes:
        """ Reads and return from I/O device a bytes block with given `size`.
        """

    @abstractmethod
    def _write_block(self, block: bytes) -> int:
        """ Writes a `bytes` block to I/O device and return number of sent bytes.
        """

    def _read_until_task(self, delimiter, max_bytes):
        if self.active:
            pos = self._in.find(delimiter)
            if (pos >= 0):
                return self.READ, self.read(pos + len(delimiter))
            elif max_bytes > 0 and len(self._in) >= max_bytes:
                return self.READ, None
            return 0, None
        else:
            return self.ERROR, None

    def setup_read_until(self, callback, delimiter, max_bytes):
        result, payload = self._read_until_task(delimiter, max_bytes)
        if not result:
            self._task = callback, self.READ, self._read_until_task, delimiter, max_bytes
        return result, payload

    def _read_number_task(self, num_bytes):
        if self.active:
            if len(self._in) >= num_bytes:
                return self.READ, self.read(num_bytes)
            return 0, None
        else:
            return self.ERROR, None

    def setup_read_number(self, callback, num_bytes):
        result, payload = self._read_number_task(num_bytes)
        if not result:
            self._task = callback, self.READ, self._read_number_task, num_bytes
        return result, payload

    def _flush_task(self):
        if self.active:
            if len(self._out) == 0:
                return self.WRITE, True
            return 0, None
        else:
            return self.ERROR, None

    def setup_flush(self, callback):
        result, payload = self._flush_task()
        if not result:
            self._task = callback, self.WRITE, self._flush_task
        return result, payload

    def cancel_task(self):
        if self._task is not None:
            self._task = None
            return True
        return False

    def read(self, max_bytes):
        """ Read bytes from incoming buffer how much is there, but not more max_bytes. """
        result, self._in = self._in[:max_bytes], self._in[max_bytes:]
        return result

    def write(self, data):
        """ Writes data to the outcoming buffer.
        Returns number of bytes what has been written.
        """
        block = b''
        if self.active:
            block = data[:self._buffer_size - len(self._out)]
            self._out += block
            if not (self._mode & self.WRITE):
                self._mode |= self.WRITE
                self._loop.update_io(self._handle, self._mode)
        return len(block)

    @abstractmethod
    def close(self):
        """ Closes this and associated resources.
        """
        self.cancel_task()
        self._loop.cancel_io(self._handle)
        self._handle = None


class SocketAutoBuffer(AutoBuffer):
    """ Socket auto buffer
    """

    def __init__(self, event_loop, socket_, block_size, buffer_size):
        self._socket = socket_
        self._socket.setblocking(0)
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
