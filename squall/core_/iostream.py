from functools import partial

from squall.core.abc import abstractmethod, IOStream as AbcIOStream
from squall.core_.abc import AutoBuffer as AbcAutoBuffer
from squall.core_.abc import EventLoop
from squall.core_.switching import Dispatcher, SwitchedCoroutine


class AutoBuffer(AbcAutoBuffer):
    """ Base I/O auto buffer
    """

    def __init__(self, event_loop: EventLoop, fd: int, block_size, buffer_size):
        self._in = b''
        self._out = b''
        self._task = None
        self._loop = event_loop
        self._mode = self.READ
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._handle = self._loop.setup_io(self._event_handler, fd, self._mode)

    @abstractmethod
    def _read_block(self, size: int) -> bytes:
        """ Reads and return from I/O device a bytes block with given `size`.
        """

    @abstractmethod
    def _write_block(self, block: bytes) -> int:
        """ Writes a `bytes` block to I/O device and return number of sent bytes.
        """

    def _event_handler(self, revents):
        last_error = None
        mode = self._mode
        if isinstance(revents, BaseException):
            last_error = revents
            revents = 0
        else:
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
                        last_error = ConnectionResetError("Connection reset by peer")
                if revents & self.WRITE:
                    block = self._out[:self._block_size]
                    if len(block) > 0:
                        sent_size = self._write_block(block)
                        self._out = self._out[sent_size:]
                    if len(self._out) == 0:
                        mode ^= self.WRITE
            except IOError as exc:
                last_error = exc

        if self._task is not None:
            # apply buffer task
            result = None
            callback, event, method, timeout = self._task
            if event & revents:
                if event == self.READ:
                    result = method()
                elif event == self.WRITE:
                    result = method()
            if result is None and last_error is not None:
                result = last_error
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
                self._loop.update_io(self._handle, self._mode)

    @property
    def active(self):
        """ See for detail `AbcAutoBuffer.active` """
        return self._handle is not None

    @property
    def READ(self):
        """ See for detail `AbcAutoBuffer.READ` """
        return self._loop.READ

    @property
    def WRITE(self):
        """ See for detail `AbcAutoBuffer.WRITE` """
        return self._loop.WRITE

    @property
    def block_size(self):
        """ See for detail `AbcAutoBuffer.block_size` """
        return self._block_size

    @property
    def buffer_size(self):
        """ See for detail `AbcAutoBuffer.buffer_size` """
        return self._buffer_size

    def setup_read_exactly(self, callback, num_bytes, timeout):
        """ See for detail `AbcAutoBuffer.read_exactly` """
        def task_method():
            if len(self._in) >= num_bytes:
                return self.read(num_bytes)
            return None
        return self._setup_task(callback, self.READ, task_method, timeout)

    def setup_read_until(self, callback, delimiter, max_bytes, timeout):
        """ See for detail `AbcAutoBuffer.read_exactly` """
        def task_method():
            result = None
            pos = self._in.find(delimiter)
            if (pos >= 0):
                result = self.read(pos + len(delimiter))
            elif max_bytes > 0 and len(self._in) >= max_bytes:
                result = BufferError("Delimiter not found, but max_bytes reached")
            return result
        return self._setup_task(callback, self.READ, task_method, timeout)

    def setup_flush(self, callback, timeout):
        def task_method():
            return True if len(self._out) == 0 else None
        return self._setup_task(callback, self.WRITE, task_method, timeout)

    def _setup_task(self, callback, trigger_event, task_method, timeout):
        """ See for detail `AbcAutoBuffer.setup_task` """
        result = None
        timeout_exc = TimeoutError("I/O timeout")
        if timeout < 0:
            result = timeout_exc
        else:
            result = task_method()
        if result is None:
            if timeout > 0:
                def callback_(revents):
                    self._event_handler(timeout_exc)
                timeout = self._loop.setup_timer(callback_, timeout)
            else:
                timeout = None
            self._task = (callback, trigger_event, task_method, timeout)
        return result

    def cancel_task(self):
        """ See for detail `AbcAutoBuffer.cancel_task` """
        if self._task is not None:
            callback, trigger_event, task_method, timeout = self._task
            if timeout is not None:
                self._loop.cancel_timer(timeout)
            self._task = None

    def read(self, max_bytes):
        """ See for detail `AbcAutoBuffer.read` """
        result, self._in = self._in[:max_bytes], self._in[max_bytes:]
        return result

    def write(self, data):
        """ See for detail `AbcAutoBuffer.write` """
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
        """ See for detail `AbcAutoBuffer.close` """
        self.cancel_task()
        self._loop.cancel_io(self._handle)
        self._handle = None


class IOStream(AbcIOStream):
    """ Base async I/O stream
    """

    def __init__(self, disp: Dispatcher, auto_buff: AutoBuffer):
        self._disp = disp
        self._auto_buff = auto_buff

    @property
    def active(self):
        """ See for detail `AbcIOStream.active` """
        return self._auto_buff.active

    @property
    def block_size(self):
        """ See for detail `AbcIOStream.block_size` """
        return self._auto_buff.block_size

    @property
    def buffer_size(self):
        """ See for detail `AbcIOStream.buffer_size` """
        return self._auto_buff.buffer_size

    def read(self, max_bytes):
        """ See for detail `AbcIOStream.read` """
        return self._auto_buff.read(max_bytes)

    def read_until(self, delimiter, *, max_bytes=None, timeout=None):
        """ See for detail `AbcIOStream.read_until` """
        return _ReadUntilCoroutine(self._disp, self._auto_buff, delimiter, max_bytes, timeout)

    def read_exactly(self, num_bytes, *, timeout=None):
        """ See for detail `AbcIOStream.read_exactly` """
        return _ReadExactly(self._disp, self._auto_buff, num_bytes, timeout)

    def write(self, data):
        """ See for detail `AbcIOStream.write` """
        return self._auto_buff.write(data)

    def flush(self, *, timeout=None):
        """ See for detail `AbcIOStream.flush` """
        return _FlushCoroutine(self._disp, self._auto_buff, timeout)

    def close(self):
        """ See for detail `AbcIOStream.close` """
        return self._auto_buff.close()


class _ReadUntilCoroutine(SwitchedCoroutine):
    """ Awaitable for `IOStream.read_until` """

    def __init__(self, disp, auto_buff, delimiter, max_bytes, timeout):
        self._auto_buff = auto_buff
        timeout = timeout or 0
        max_bytes = max_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        max_bytes = max_bytes if max_bytes > 0 else auto_buff.buffer_size
        max_bytes = max_bytes if max_bytes < auto_buff.buffer_size else auto_buff.buffer_size
        assert isinstance(delimiter, bytes) and len(delimiter) > 0
        assert isinstance(max_bytes, int) and max_bytes > 0
        assert isinstance(timeout, (int, float))
        super().__init__(disp, delimiter, max_bytes, timeout)

    def setup(self, callback, delimiter, max_bytes, timeout):
        result = self._auto_buff.setup_read_until(callback, delimiter, max_bytes, timeout)
        if result is not None:
            return result

    def cancel(self, ):
        self._auto_buff.cancel_task()


class _ReadExactly(SwitchedCoroutine):
    """ Awaitable for `IOStream.read_exactly` """

    def __init__(self, disp, auto_buff, num_bytes, timeout):
        self._auto_buff = auto_buff
        timeout = timeout or 0
        num_bytes = num_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        num_bytes = num_bytes if num_bytes < auto_buff.buffer_size else auto_buff.buffer_size
        assert isinstance(num_bytes, int) and num_bytes > 0
        assert isinstance(timeout, (int, float))
        super().__init__(disp, num_bytes, timeout)

    def setup(self, callback, num_bytes, timeout):
        result = self._auto_buff.setup_read_exactly(callback, num_bytes, timeout)
        if result is not None:
            return result

    def cancel(self):
        self._auto_buff.cancel_task()


class _FlushCoroutine(SwitchedCoroutine):
    """ Awaitable for `IOStream.flush` """

    def __init__(self, disp, auto_buff, timeout):
        self._auto_buff = auto_buff
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        super().__init__(disp, timeout)

    def setup(self, callback, timeout):
        result = self._auto_buff.setup_flush(callback, timeout)
        if result is not None:
            return result

    def cancel(self):
        self._auto_buff.cancel_task()
