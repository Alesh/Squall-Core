""" Async I/O stream buffers used callbacks
"""
import os
import errno
from squall.core_callback.eventloop import EventLoop
from squall.core_callback.buffers import InBuffer, OutBuffer


class EventBuffer(object):
    """ Event-driven base I/O stream buffer
    """
    READ = EventLoop.READ
    WRITE = EventLoop.WRITE
    ERROR = EventLoop.ERROR

    def __init__(self, loop, fd, block_size=0, buffer_size=0):
        self._fd = fd
        self._loop = loop
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._adjust_buffer_size()
        self._in = InBuffer(self._read_block, self._block_size, self._buffer_size)
        self._out = OutBuffer(self._write_block, self._block_size, self._buffer_size)
        self._flush_callback = None
        self._read_callback = None
        self._handle = None
        self._mode = 0
        self.mode = self.READ

    @property
    def fd(self):
        """ File descriptor """
        return self._fd

    @property
    def active(self):
        """ Return `True` if active """
        return self._fd >= 0

    @property
    def event_loop(self):
        """ Event loop accosiated with buffer """
        return self._loop

    @property
    def mode(self):
        """ Current watching mode """
        return self._mode

    @mode.setter
    def mode(self, value):
        if self.active:
            if self._handle is None:
                self._handle = self._loop.setup_io(self._event_handler, self._fd, value)
                if self._handle is not None:
                    self._mode = value
            elif value != self._mode:
                if self._loop.update_io(self._handle, value):
                    self._mode = value

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
        """ Sets up buffer to read_exactly

        Returns:
            (tuple): tuple containing:
                early (bool): `True` if result already available
                result (object): read data block
                                `LookupError` if `delimiter` not found but `max_number` reached or
                                 `None` if cannot set up watching
                                 when `early` == `True` otherwise does not matter
        """
        if not self.active:
            return True, None
        max_number = max_number or self.buffer_size
        self._read_callback = callback
        result = self._in.setup(max_number, delimiter)
        if result:
            self.cancel(self.READ)
            if result > 0:
                return True, self._in.read(result)
            return True, LookupError("`delimiter` not found but `max_number`")
        self.mode |= self.READ
        return False, None

    def setup_read_exactly(self, callback, number):
        """ Sets up buffer to read_exactly

        Returns:
            (tuple): tuple containing:
                early (bool): `True` if result already available
                result (object): read data block
                                 `None` if cannot set up watching
                                 when `early` == `True` otherwise does not matter
        """
        if not self.active:
            return True, None
        self._read_callback = callback
        result = self._in.setup(number)
        if result > 0:
            self.cancel(self.READ)
            return True, self._in.read(result)
        self.mode |= self.READ
        return False, None

    def read(self, number):
        """ Read bytes from incoming buffer how much is there, but not more `number`.

        Return:
            bytes: result
        """
        if self.active:
            return self._in.read(number)
        return b''

    def setup_flush(self, callback):
        """ Sets up buffer to flush

        Returns:
            (tuple): tuple containing:
                early (bool): `True` if result already present
                result (object): `True` if buffer has flushed;
                                 `None` if cannot set up watching
                                  when `early` == `True` otherwise does not matter
        """
        if not self.active:
            return True, None
        self._flush_callback = callback
        result = self._out.setup(0)
        if result == 1:
            self.cancel(self.WRITE)
            return True, True
        return False, None

    def write(self, data):
        """ Writes data to the outcoming buffer.

        Returns:
            int: number of written bytes.
        """
        if self.active:
            self.mode |= self.WRITE
            return self._out.write(data)
        return 0

    def cancel(self, mode):
        """ Cancels a buffer event watching. """
        if mode & self.READ:
            self._read_callback = None
            self._in.cancel()
        if mode & self.WRITE:
            self._flush_callback = None
            self._out.cancel()

    def cleanup(self):
        """ Deactivate and cleanups buffer. """
        self.mode = 0
        self._fd = -1
        self._loop = None
        self._in.cleanup()
        self._out.cleanup()

    def _event_handler(self, revents):
        in_result = out_result = None
        if revents & self.ERROR:
            in_result = self._in(self.ERROR)
            out_result = self._out(self.ERROR)
        else:
            if revents & self.READ:
                try:
                    in_result = self._in(self.READ)
                except Exception as exc:
                    in_result = 0, True, exc
            if revents & self.WRITE:
                try:
                    out_result = self._out(self.WRITE)
                except Exception as exc:
                    out_result = 0, True, exc

        if in_result is not None:
            result, pause, error = in_result
            if self._read_callback is not None:
                event = None
                callback = self._read_callback
                if result:
                    if result > 0:
                        event = self._in.read(result)
                    else:
                        event = LookupError("`delimiter` not found but `max_number`")
                else:
                    if isinstance(error, Exception):
                        event = error
                    elif error > 0:
                        event = IOError(error, os.strerror(error))
                if event is not None:
                    self.cancel(self.READ)
                    callback(event)
                    if self.active:
                        pause = (self.incoming_size >= self.buffer_size)
            if pause:
                if revents & self.READ:
                    self.mode ^= self.READ
            else:
                if not revents & self.READ:
                    self.mode |= self.READ

        if out_result is not None:
            result, pause, error = out_result
            if self._flush_callback is not None:
                event = None
                callback = self._flush_callback
                if result == 1:
                    event = True
                else:
                    if isinstance(error, Exception):
                        event = error
                    elif error > 0:
                        event = IOError(error, os.strerror(error))
                if event is not None:
                    self.cancel(self.WRITE)
                    callback(event)
                    if self.active:
                        pause = (self.outcoming_size == 0)
            if pause:
                if revents & self.WRITE:
                    self.mode ^= self.WRITE
            else:
                if not revents & self.WRITE:
                    self.mode |= self.WRITE

    def _adjust_buffer_size(self):
        self._block_size = self._block_size if self._block_size > 1024 else 1024
        self._block_size += 1024 if (self._block_size % 1024) else 0
        self._block_size = int(self._block_size / 1024) * 1024
        self._buffer_size = self._buffer_size if self._buffer_size > 1024 * 4 else 1024 * 4
        self._buffer_size = int(self._buffer_size / self._block_size) * self._block_size

    def _read_block(self, size):
        raise NotImplementedError("Metod `_read_block` must be implemented")
        # return block, errno

    def _write_block(self, block):
        raise NotImplementedError("Metod `_write_block` must be implemented")
        # return sent, errno


class SocketBuffer(EventBuffer):
    """ Socket auto buffer
    """

    def __init__(self, loop, socket_, block_size, buffer_size):
        self._socket = socket_
        self._socket.setblocking(0)
        super().__init__(loop, socket_.fileno(), block_size, buffer_size)

    def _read_block(self, size):
        try:
            block = self._socket.recv(size)
            if block:
                return block, 0
            return block, errno.ECONNRESET
        except IOError as exc:
            return b'', exc.errno or errno.EIO

    def _write_block(self, block):
        try:
            sent = self._socket.send(block)
            return sent, 0
        except IOError as exc:
            return 0, exc.errno or errno.EIO


class FileBuffer(EventBuffer):
    """ File auto buffer
    """
    def _read_block(self, size):
        try:
            block = os.read(self.fd, size)
            if block:
                return block, 0
            raise EOFError("End of file")
        except IOError as exc:
            return b'', exc.errno or errno.EIO

    def _write_block(self, block):
        try:
            sent = os.write(self.fd, block)
            return sent, 0
        except IOError as exc:
            return 0, exc.errno or errno.EIO
