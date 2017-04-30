""" Async I/O streams
"""
import os
import errno
from squall.core.switching import EventLoopError
from squall.core.switching import CannotSetupWatching, _Awaitable


class IOStream(object):
    """ Base async I/O stream
    """

    def __init__(self, auto_buff):
        self._auto_buff = auto_buff

    @property
    def active(self):
        """ Returns `True` if this stream is active (not closed).
        """
        return self._auto_buff.is_active

    @property
    def block_size(self):
        """ Size of block of data reads/writes to the I/O device at once.
        """
        return self._auto_buff.block_size

    @property
    def buffer_size(self):
        """ Maximum size of the read/write buffers.
        """
        return self._auto_buff.buffer_size

    def read(self, max_bytes):
        """ Read bytes from incoming buffer how much is there, but not more max_bytes.
        """
        return self._auto_buff.read(max_bytes)

    def read_until(self, delimiter, *, max_bytes=None, timeout=None):
        """ Returns awaitable to asynchronously read until we have found the given
        delimiter. The result includes all the data read including the delimiter.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            LookupError: incoming buffer size equal or greater `max_bytes` but delimiter not found.
            IOError: occurred any I/O error.
        """

        timeout = timeout or 0
        max_bytes = max_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        max_bytes = max_bytes if max_bytes > 0 else self._auto_buff.buffer_size
        max_bytes = max_bytes if max_bytes < self._auto_buff.buffer_size else self._auto_buff.buffer_size
        assert isinstance(delimiter, bytes) and len(delimiter) > 0
        assert isinstance(max_bytes, int) and max_bytes > 0
        assert isinstance(timeout, (int, float))
        return _ReadUntilAwaitable(self._auto_buff, delimiter, max_bytes, timeout)

    def read_exactly(self, num_bytes, *, timeout=None):
        """ Returns awaitable to asynchronously read a number of bytes.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """
        timeout = timeout or 0
        num_bytes = num_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        num_bytes = num_bytes if num_bytes < self._auto_buff.buffer_size else self._auto_buff.buffer_size
        assert isinstance(num_bytes, int) and num_bytes > 0
        assert isinstance(timeout, (int, float))
        return _ReadExactlyAwaitable(self._auto_buff, num_bytes, timeout)

    def write(self, data):
        """ Writes data to the outcoming buffer of this stream.

        Returns:
            number of bytes what has been written.
        """
        return self._auto_buff.write(data)

    def flush(self, *, timeout=None):
        """ Returns awaitable to asynchronously drain an outcoming buffer of this stream.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        return _FlushAwaitable(self._auto_buff, timeout)

    def close(self):
        """ Closes stream and associated resources.
        """
        return self._auto_buff.close()


class _ReadUntilAwaitable(_Awaitable):
    """ Creates and returns awaitable for `IOStream.read_until`
    """
    def __init__(self, auto_buff, delimiter, max_bytes, timeout):
        self._auto_buff = auto_buff
        self._loop = auto_buff._loop
        super().__init__(delimiter, max_bytes, timeout)

    def _on_event(self, revents, payload=None):
        if revents == self._auto_buff.READ:
            if payload is not None:
                self._callback(payload)
            else:
                self._callback(LookupError("`delimiter` not found but `max_size`"))
        elif revents == self._loop.TIMEOUT:
            self._callback(TimeoutError("I/O timeout"))
        else:
            if payload:
                self._callback(IOError(payload, os.strerror(payload)))
            else:
                self._callback(EventLoopError)

    def setup(self, delimiter, max_bytes, timeout):
        if timeout < 0:
            return TimeoutError("I/O timeout"),
        result, payload = self._auto_buff.setup_read_until(self._on_event, delimiter, max_bytes)
        if result:
            if result == self._auto_buff.READ:
                if payload is not None:
                    return payload,
                else:
                    return LookupError("`delimiter` not found but `max_size`"),
            else:
                return IOError(errno.EIO, os.strerror(errno.EIO))
        else:
            timeout_handle = None
            if timeout > 0:
                timeout_handle = self._loop.setup_timer(self._on_event, timeout)
                if timeout_handle is None:
                    self._auto_buff.cancel_task()
                    return CannotSetupWatching(),
            return None, timeout_handle
        return CannotSetupWatching(),

    def cancel(self, timeout_handle):
        self._auto_buff.cancel_task()
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)


class _ReadExactlyAwaitable(_Awaitable):
    """ Creates and returns awaitable for `IOStream.read_until`
    """
    def __init__(self, auto_buff, num_bytes, timeout):
        self._auto_buff = auto_buff
        self._loop = auto_buff._loop
        super().__init__(num_bytes, timeout)

    def _on_event(self, revents, payload=None):
        if revents == self._auto_buff.READ:
            self._callback(payload)
        elif revents == self._loop.TIMEOUT:
            self._callback(TimeoutError("I/O timeout"))
        else:
            if payload:
                self._callback(IOError(payload, os.strerror(payload)))
            else:
                self._callback(EventLoopError)

    def setup(self, num_bytes, timeout):
        if timeout < 0:
            return TimeoutError("I/O timeout"),
        result, payload = self._auto_buff.setup_read_exactly(self._on_event, num_bytes)
        if result:
            if result == self._auto_buff.READ:
                return payload,
            else:
                return IOError(errno.EIO, os.strerror(errno.EIO))
        else:
            timeout_handle = None
            if timeout > 0:
                timeout_handle = self._loop.setup_timer(self._on_event, timeout)
                if timeout_handle is None:
                    self._auto_buff.cancel_task()
                    return CannotSetupWatching(),
            return None, timeout_handle
        return CannotSetupWatching(),

    def cancel(self, timeout_handle):
        self._auto_buff.cancel_task()
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)


class _FlushAwaitable(_Awaitable):
    """ Creates and returns awaitable for `IOStream.read_until`
    """
    def __init__(self, auto_buff, timeout):
        self._auto_buff = auto_buff
        self._loop = auto_buff._loop
        super().__init__(timeout)

    def _on_event(self, revents, payload=None):
        if revents == self._auto_buff.WRITE:
            self._callback(True)
        elif revents == self._loop.TIMEOUT:
            self._callback(TimeoutError("I/O timeout"))
        else:
            if payload:
                self._callback(IOError(payload, os.strerror(payload)))
            else:
                self._callback(EventLoopError)

    def setup(self, timeout):
        if timeout < 0:
            return TimeoutError("I/O timeout"),
        result, payload = self._auto_buff.setup_flush(self._on_event)
        if result:
            if result == self._auto_buff.WRITE:
                return True,
            else:
                return IOError(errno.EIO, os.strerror(errno.EIO))
        else:
            timeout_handle = None
            if timeout > 0:
                timeout_handle = self._loop.setup_timer(self._on_event, timeout)
                if timeout_handle is None:
                    self._auto_buff.cancel_task()
                    return CannotSetupWatching(),
            return None, timeout_handle
        return CannotSetupWatching(),

    def cancel(self, timeout_handle):
        self._auto_buff.cancel_task()
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)
