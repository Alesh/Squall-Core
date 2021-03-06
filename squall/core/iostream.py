""" Async I/O streams
"""
import os
from socket import SHUT_RDWR
from .switching import Awaitable

try:
    from squall.core_callback import SocketBuffer, FileBuffer
except ImportError:
    from .callback import SocketBuffer, FileBuffer


class IOStream(object):
    """ Base async I/O stream
    """

    def __init__(self, disp, event_buffer):
        self._disp = disp
        self._buff = event_buffer
        self._is_closed = False

    @property
    def fd(self):
        """ Returns stream file descriptor.
        """
        return self._buff.fd

    @property
    def active(self):
        """ Returns `True` if this stream is active (not closed).
        """
        return not self._is_closed

    @property
    def block_size(self):
        """ Size of data block for read/write to the I/O device at once.
        """
        return self._buff.block_size

    @property
    def buffer_size(self):
        """ Maximum size of the read/write buffers.
        """
        return self._buff.buffer_size

    @property
    def incoming_size(self):
        """ Incomming buffer size """
        return self._buff.incoming_size

    @property
    def outcoming_size(self):
        """ Outcomming buffer size """
        return self._buff.outcoming_size

    def read(self, max_bytes):
        """ Read bytes from incoming buffer how much is there, but not more max_bytes.

        Returns:
            block of read bytes
        """
        return self._buff.read(max_bytes)

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
        assert isinstance(timeout, (int, float))
        assert isinstance(delimiter, bytes) and delimiter
        assert isinstance(max_bytes, int) and max_bytes >= 0
        return _ReadUntilAwaitable(self._disp, self._buff, delimiter, max_bytes, timeout)

    def read_exactly(self, num_bytes, *, timeout=None):
        """ Returns awaitable to asynchronously read a number of bytes.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """
        timeout = timeout or 0
        num_bytes = num_bytes or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(num_bytes, int) and num_bytes > 0
        assert isinstance(timeout, (int, float))
        return _ReadExactlyAwaitable(self._disp, self._buff, num_bytes, timeout)

    def write(self, data):
        """ Writes data to the outcoming buffer of this stream.

        Returns:
            number of written bytes.
        """
        return self._buff.write(data)

    def flush(self, *, timeout=None):
        """ Returns awaitable to asynchronously drain an outcoming buffer of this stream.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        return _FlushAwaitable(self._disp, self._buff, timeout)

    def close(self):
        """ Closes stream and associated resources.
        """
        self._buff.release()
        self._is_closed = True


class _ReadUntilAwaitable(Awaitable):
    """ Awaitable that returns `IOStream.read_until`
    """

    def __init__(self, disp, buff, delimiter, max_bytes, timeout):
        self._buff = buff
        super().__init__(disp, delimiter, max_bytes, timeout)

    def _setup(self, delimiter, max_bytes, timeout):
        timeout_handle = None
        try:
            if timeout < 0:
                raise TimeoutError("I/O timeout")
            elif timeout > 0:
                timeout_handle = self._loop.setup_timer(self._callback, timeout)
            result = self._buff.setup_read_until(self._callback, delimiter, max_bytes)
            return result, self._buff.cancel_read, timeout_handle
        except Exception as exc:
            return exc, self._buff.cancel_read, timeout_handle

    def _cancel(self, cancel_read, timeout_handle=None):
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)
        cancel_read()


class _ReadExactlyAwaitable(Awaitable):
    """ Awaitable that returns `IOStream.read_exactly`
    """

    def __init__(self, disp, buff, num_bytes, timeout):
        self._buff = buff
        super().__init__(disp, num_bytes, timeout)

    def _setup(self, num_bytes, timeout):
        timeout_handle = None
        try:
            if timeout < 0:
                raise TimeoutError("I/O timeout")
            elif timeout > 0:
                timeout_handle = self._loop.setup_timer(self._callback, timeout)
            result = self._buff.setup_read_exactly(self._callback, num_bytes)
            return result, self._buff.cancel_read, timeout_handle
        except Exception as exc:
            return exc, self._buff.cancel_read, timeout_handle

    def _cancel(self, cancel_read, timeout_handle=None):
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)
        cancel_read()


class _FlushAwaitable(Awaitable):
    """ Awaitable that returns `IOStream.flush`
    """

    def __init__(self, disp, buff, timeout):
        self._buff = buff
        super().__init__(disp, timeout)

    def _setup(self, timeout):
        timeout_handle = None
        try:
            if timeout < 0:
                raise TimeoutError("I/O timeout")
            elif timeout > 0:
                timeout_handle = self._loop.setup_timer(self._callback, timeout)
            result = self._buff.setup_flush(self._callback)
            return result, self._buff.cancel_flush, timeout_handle
        except Exception as exc:
            return exc, self._buff.cancel_flush, timeout_handle

    def _cancel(self, cancel_flush, timeout_handle=None):
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)
        cancel_flush()


class SocketStream(IOStream):
    """ Async socket I/O stream
    """

    def __init__(self, disp, socket_, block_size, buffer_size):
        self._socket = socket_
        super().__init__(disp, SocketBuffer(disp._loop, socket_, block_size, buffer_size))

    def close(self):
        """ Closes stream and associated resources.
        """
        super().close()
        try:
            self._socket.shutdown(SHUT_RDWR)
        except IOError:
            pass
        finally:
            self._socket.close()


class FileStream(IOStream):
    """ Async file I/O stream
    """

    def __init__(self, disp, path, flags, *, mode=0o777, block_size=0, buffer_size=0):
        self._fd = os.open(path, flags | os.O_NONBLOCK, mode)
        super().__init__(disp, FileBuffer(disp._loop, self._fd, block_size, buffer_size))

    def close(self):
        """ Closes stream and associated resources.
        """
        super().close()
        os.close(self._fd)
