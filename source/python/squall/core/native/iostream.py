from squall.core.abc import IOStream as AbcIOStream
from squall.core.native.cb.abc import AutoBuffer as AbcAutoBuffer
from squall.core.native.switching import Switcher, SwitchedCoroutine


class IOStream(AbcIOStream):
    """ Base async I/O stream
    """

    def __init__(self, switcher: Switcher, auto_buff: AbcAutoBuffer):
        self._switcher = switcher
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
        timeout = timeout or 0
        max_bytes = max_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        max_bytes = max_bytes if max_bytes > 0 else self.buffer_size
        max_bytes = max_bytes if max_bytes < self.buffer_size else self.buffer_size
        assert isinstance(delimiter, bytes) and len(delimiter) > 0
        assert isinstance(max_bytes, int) and max_bytes > 0
        assert isinstance(timeout, (int, float))

        def task_method(incoming_buffer):
            result = None
            pos = incoming_buffer.find(delimiter)
            if (pos >= 0):
                result = self._auto_buff.read(pos + len(delimiter))
            elif max_bytes > 0 and len(incoming_buffer) >= max_bytes:
                result = BufferError("Delimiter not found, but max_bytes reached")
            return result

        def setup(callback):
            result = self._auto_buff.setup_task(callback, self._auto_buff.READ, task_method, timeout)
            if result is not None:
                return result

        def cancel():
            self._auto_buff.cancel_task()

        return SwitchedCoroutine(self._switcher, setup, cancel)

    def read_exactly(self, num_bytes, *, timeout=None):
        """ See more: `abc.IOStream.read_exactly` """
        timeout = timeout or 0
        num_bytes = num_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        num_bytes = num_bytes if num_bytes < self.buffer_size else self.buffer_size
        assert isinstance(num_bytes, int) and num_bytes > 0
        assert isinstance(timeout, (int, float))

        def task_method(incoming_buffer):
            result = None
            if len(incoming_buffer) >= num_bytes:
                result = self._auto_buff.read(num_bytes)
            return result

        def setup(callback):
            result = self._auto_buff.setup_task(callback, self._auto_buff.READ, task_method, timeout)
            if result is not None:
                return result

        def cancel():
            self._auto_buff.cancel_task()

        return SwitchedCoroutine(self._switcher, setup, cancel)

    def write(self, data):
        """ See more: `abc.IOStream.write` """
        return self._auto_buff.write(data)

    def flush(self, *, timeout=None):
        """ See more: `abc.IOStream.flush` """
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))

        def task_method(outcoming_buffer_size):
            return True if outcoming_buffer_size == 0 else None

        def setup(callback):
            result = self._auto_buff.setup_task(callback, self._auto_buff.WRITE, task_method, timeout)
            if result is not None:
                return result

        def cancel():
            self._auto_buff.cancel_task()

        return SwitchedCoroutine(self._switcher, setup, cancel)

    def close(self):
        """ See more: `abc.IOStream.close` """
        return self._auto_buff.close()
