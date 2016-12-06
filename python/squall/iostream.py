"""
Event-driven async/await I/O stream.
"""
from squall import abc
from squall.coroutine import Dispatcher, _Awaitable


class IOStream(object):
    """ Base class for async I/O streams.
    """

    def __init__(self, disp, autobuff):
        assert isinstance(disp, Dispatcher)
        assert isinstance(autobuff, abc.AutoBuffer)
        self._autobuff = autobuff
        self._finalize = False
        self._closed = False
        self._disp = disp

    @property
    def closed(self):
        """ Returns `True` if this stream is closed.
        """
        return self._closed or self._finalize

    @property
    def flushed(self):
        """ Returns `True` if this stream is flushed.
        """
        return self._closed or (not self._autobuff.writing)

    @property
    def block_size(self):
        """ The block size of data reads / writes to the I/O device at once.
        """
        return self._autobuff.block_size

    @property
    def buffer_size(self):
        """ Maximum size of the incoming / outcoming data buffers.
        """
        return self._autobuff.max_size

    @property
    def last_error(self):
        """ Returns last occurred error.
        """
        return self._autobuff.last_error

    def read_bytes(self, number, *, timeout=None):
        """ Returns awaitable which switch back when a autobuffer has
        given `number` of bytes or timeout exceeded if it set.
        Awaitable returns requested numbers of bytes
        or raises `TimeoutError` or `IOError`.
        """
        _, disp = Dispatcher.current()
        assert disp == self._disp
        event_disp = disp._event_disp
        assert isinstance(number, int)
        number = (number
                  if number > 0 and number <= self.buffer_size
                  else self.buffer_size)
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))

        def cancel(callback):
            if timeout > 0:
                event_disp.cancel(callback)
            self._autobuff.cancel()

        def setup(callback, number, timeout):
            result = True
            if timeout > 0:
                result = event_disp.watch_timer(callback, timeout)
            if result:
                result = self._autobuff.watch_read_bytes(callback, number)
            if not result:
                cancel(callback)
            return result

        if self._finalize or self._closed:
            raise ConnectionError("Connection has closed")
        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(cancel, setup, number, timeout=timeout)

    def read_until(self, delimiter, *, max_number=None, timeout=None):
        """ Returns awaitable which switch back when a autobuffer has
        given `delimiter` or `max_number` of bytes or timeout exceeded
        if it set.
        Awaitable returns block of bytes ends with `delimiter` or
        `max_number` of bytes or raises `TimeoutError` or `IOError`.
        """
        _, disp = Dispatcher.current()
        assert disp == self._disp, "{} != {}".format(disp, self._disp)
        event_disp = disp._event_disp
        assert isinstance(delimiter, bytes)
        max_number = max_number or 0
        assert isinstance(max_number, int)
        max_number = (max_number
                      if max_number > 0 and max_number <= self.buffer_size
                      else self.buffer_size)
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))

        def cancel(callback):
            if timeout > 0:
                event_disp.cancel(callback)
            self._autobuff.cancel()

        def setup(callback, delimiter, max_number, timeout):
            result = True
            if timeout > 0:
                result = event_disp.watch_timer(callback, timeout)
            if result:
                result = self._autobuff.watch_read_until(callback, delimiter,
                                                         max_number)
            if not result:
                cancel(callback)
            return result

        if self._finalize or self._closed:
            raise ConnectionError("Connection has closed")
        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(cancel, setup,
                          delimiter, max_number, timeout=timeout)

    def flush(self, *, timeout=None):
        """ Returns awaitable which switch back when a autobuffer will
        complete drain outcoming buffer or timeout exceeded if it set.
        Awaitable returns insignificant value
        or raises `TimeoutError` or `IOError`.
        """
        _, disp = Dispatcher.current()
        assert disp == self._disp
        event_disp = disp._event_disp
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))

        def cancel(callback):
            if timeout > 0:
                event_disp.cancel(callback)
            self._autobuff.cancel()

        def setup(callback, timeout):
            result = True
            if timeout > 0:
                result = event_disp.watch_timer(callback, timeout)
            if result:
                result = self._autobuff.watch_flush(callback)
            if not result:
                cancel(callback)
            return result

        if self._closed and not self._finalize:
            raise ConnectionError("Connection has closed")
        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(cancel, setup, timeout=timeout)

    def write(self, data):
        """ Puts `data` bytes to outcoming buffer.
        """
        if self._finalize or self._closed:
            raise ConnectionError("Connection has closed")
        assert isinstance(data, bytes)
        return self._autobuff.write(data)

    async def close(self, timeout=None):
        """ Closes a stream asynchronously.
        """
        if not self._closed:
            if not self._finalize:
                self._finalize = True
                await self.flush(timeout=timeout)
                self.abort()

    def abort(self):
        """ Closes a stream and releases resources immediately.
        """
        if not self._closed:
            self._closed = True
            self._autobuff.release()
