from functools import partial

from squall.core.abc import IOStream as AbcIOStream
from squall.core.native.cb.abc import AutoBuffer as AbcAutoBuffer
from squall.core.native.switching import Dispatcher, SwitchedCoroutine


class IOStream(AbcIOStream):
    """ Base async I/O stream
    """

    def __init__(self, disp: Dispatcher, auto_buff: AbcAutoBuffer):
        self._disp = disp
        self._auto_buff = auto_buff

    @property
    def active(self):
        """ See more: `abc.IOStream.active` """
        return self._auto_buff.active

    @property
    def block_size(self):
        """ See more: `abc.IOStream.block_size` """
        return self._auto_buff.block_size

    @property
    def buffer_size(self):
        """ See more: `abc.IOStream.buffer_size` """
        return self._auto_buff.buffer_size

    def read(self, max_bytes):
        """ See more: `abc.IOStream.read` """
        return self._auto_buff.read(max_bytes)

    def read_until(self, delimiter, *, max_bytes=None, timeout=None):
        """ See more: `abc.IOStream.read_until` """
        return _ReadUntilCoroutine(self._disp, self._auto_buff, delimiter, max_bytes, timeout)

    def read_exactly(self, num_bytes, *, timeout=None):
        """ See more: `abc.IOStream.read_exactly` """
        return _ReadExactly(self._disp, self._auto_buff, num_bytes, timeout)

    def write(self, data):
        """ See more: `abc.IOStream.write` """
        return self._auto_buff.write(data)

    def flush(self, *, timeout=None):
        """ See more: `abc.IOStream.flush` """
        return _FlushCoroutine(self._disp, self._auto_buff, timeout)

    def close(self):
        """ See more: `abc.IOStream.close` """
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

    def task_method(self, delimiter, max_bytes, incoming_buffer):
        result = None
        pos = incoming_buffer.find(delimiter)
        if (pos >= 0):
            result = self._auto_buff.read(pos + len(delimiter))
        elif max_bytes > 0 and len(incoming_buffer) >= max_bytes:
            result = BufferError("Delimiter not found, but max_bytes reached")
        return result

    def setup(self, callback, delimiter, max_bytes, timeout):
        task_method = partial(self.task_method, delimiter, max_bytes)
        result = self._auto_buff.setup_task(callback, self._auto_buff.READ, task_method, timeout)
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

    def task_method(self, num_bytes, incoming_buffer):
        result = None
        if len(incoming_buffer) >= num_bytes:
            result = self._auto_buff.read(num_bytes)
        return result

    def setup(self, callback, num_bytes, timeout):
        task_method = partial(self.task_method, num_bytes)
        result = self._auto_buff.setup_task(callback, self._auto_buff.READ, task_method, timeout)
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

    def task_method(self, outcoming_buffer_size):
        return True if outcoming_buffer_size == 0 else None

    def setup(self, callback, timeout):
        result = self._auto_buff.setup_task(callback, self._auto_buff.WRITE, self.task_method, timeout)
        if result is not None:
            return result

    def cancel(self):
        self._auto_buff.cancel_task()
