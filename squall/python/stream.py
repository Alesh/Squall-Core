"""
This module contains implementation of asynchronous streams.
"""
import socket

from _squall import StreamAutoBuffer
from squall.coroutine import _SwitchBack


class IOStream(object):

    """ Base class for asynchronous I/O stream.
    """

    def __init__(self, auto_buffer):
        self._active = True
        self._auff = auto_buffer

    @property
    def active(self):
        """ Return `True` if stream is active. """
        return self._active

    async def read_bytes(self, num_bytes, *, timeout=None):
        """ Asynchronously reads a number of bytes.
        """
        assert self.active
        assert isinstance(num_bytes, int) and num_bytes >= 0
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        num_bytes = (self._auff.max_size
                     if num_bytes > self._auff.max_size else num_bytes)
        result = self._auff.read_bytes(num_bytes)
        if result:
            return result
        return await _SwitchBack(self._auff.setup_read_bytes, num_bytes,
                                 timeout=float(timeout or 0))

    async def read_until(self, delimiter, *, timeout=None, max_bytes=None):
        """ Asynchronously reads until we have found the given delimiter.
        """
        assert self.active
        assert isinstance(delimiter, bytes)
        assert (isinstance(max_bytes, int) and
                max_bytes >= 0) or max_bytes is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        max_bytes = (self._auff.max_size
                     if max_bytes is None or max_bytes > self._auff.max_size
                     else max_bytes)
        result = self._auff.read_until(delimiter, max_bytes)
        if result:
            return result
        return await _SwitchBack(self._auff.setup_read_until, delimiter,
                                 max_bytes, timeout=float(timeout or 0))

    async def write(self, data=None, *, timeout=None, flush=False):
        """ Asynchronously writes outgoing data.
        """
        assert self.active
        assert isinstance(data, bytes) or data is None
        assert ((isinstance(timeout, (int, float)) and
                timeout >= 0) or timeout is None)
        written = self._auff.write(data) if data else 0
        if self._auff.outfilling < 0.5 and not flush:
            return written
        else:
            if self._auff.flush():
                return written
        await _SwitchBack(self._auff.setup_flush, timeout=float(timeout or 0))
        return written

    def close(self):
        """ Closes stream.
        """
        if self.active:
            self._active = False
            self._auff.cleanup()


class SocketStream(IOStream):

    """ Asynchronous socket stream.
    """

    def __init__(self, socket_, chunk_size=8192, buffer_size=262144):
        self._socket = socket_
        self._peername = socket_.getpeername()
        self._sockname = socket_.getsockname()
        super(SocketStream, self).__init__(
            StreamAutoBuffer(socket_, chunk_size, buffer_size))

    @property
    def sockname(self):
        """ Local network name """
        return self._sockname

    @property
    def peername(self):
        """ Remote network name """
        return self._peername

    @property
    def buffer_size(self):
        """ Maximum buffer size """
        return self._auff.max_size

    @property
    def chunk_size(self):
        """ Buffer chunk size """
        return self._auff.chunk_size

    def close(self):
        """ Closes stream.
        """
        if self.active:
            super(SocketStream, self).close()
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            finally:
                self._socket.close()
