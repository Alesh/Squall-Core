""" Failback I/O autobuffer classes.
"""
import errno
import socket
from functools import partial

from squall.coroutine import dispatcher, ERROR, READ, WRITE


class SocketAutoBuffer(object):

    """ Socket buffer with auto fill/drain.
    """

    def __init__(self, socket_, chunk_size=8192, max_size=262144):
        self._mask = 0
        self._exc = None
        self._task = None
        self._inbuff = b''
        self._outbuff = b''
        self._active = True
        self._socket = socket_
        self._fd = socket_.fileno()
        self._socket.setblocking(0)
        self._chunk_size = chunk_size
        self._max_size = max_size
        self.running = READ

    @property
    def closed(self):
        """ Return true if cstreram is closed. """
        return not self._active

    @property
    def size(self):
        """ Current size of outgoing buffer. """
        return len(self._outbuff)

    @property
    def max_size(self):
        """ Maximum buffers size"""
        return self._max_size

    @property
    def chunk_size(self):
        """ Buffers chunk size"""
        return self._chunk_size

    @property
    def running(self):
        """ Autobuffering state. """
        return self._mask

    @running.setter
    def running(self, value):
        prev_mask = self._mask
        if value < 0 and (value & self._mask) == value:
            self._mask = self._mask ^ value
        elif value > 0:
            self._mask = self._mask | value
        else:
            self._mask = 0
        if prev_mask != self._mask:

            if self._mask > 0:
                dispatcher.setup_wait_io(self, self._fd, self._mask)
            else:
                dispatcher.disable_watching(self)

    def __call__(self, events):
        if ERROR & events:
            self._exc = IOError("Unexpected I/O loop error")
            self.running = 0
        else:
            try:
                if READ & events:
                    data = self._socket.recv(self._chunk_size)
                    if len(data) > 0:
                        self._inbuff += data
                        if len(self._inbuff) >= self._max_size:
                            self.running = -READ
                    else:
                        self._exc = ConnectionResetError(
                            errno.ECONNRESET, "Connection reset by peer")
                if WRITE & events and len(self._outbuff) > 0:
                    sent = self._socket.send(self._outbuff[:self._chunk_size])
                    if sent > 0:
                        self._outbuff = self._outbuff[sent:]
                        if len(self._outbuff) == 0:
                            self.running = -WRITE
                    else:
                        self._exc = ConnectionResetError(
                            errno.ECONNRESET, "Connection reset by peer")
            except IOError as exc:
                self._exc = exc
        done = self.check_task()
        if done:
            self.reset_task()
            target, events, payload = done
            target(events, payload)
        return True

    def check_read_bytes(self, target, max_bytes):
        if self._exc is not None:
            self._task = None
            exc, self._exc = self._exc, None
            return target, ERROR, exc
        elif len(self._inbuff) >= max_bytes:
            self._task = None
            data = self._inbuff[:max_bytes]
            self._inbuff = self._inbuff[max_bytes:]
            return target, READ, data
        return None

    def setup_read_bytes(self, target, max_bytes):
        self.running = READ
        self._task = partial(self.check_read_bytes, target, max_bytes)

    def check_read_until(self, target, delimiter, max_bytes):
        if self._exc is not None:
            self._task = None
            exc, self._exc = self._exc, None
            return target, ERROR, exc
        else:
            pos = self._inbuff.find(delimiter)
            if pos >= 0:
                self._task = None
                pos += len(delimiter)
                data = self._inbuff[:pos]
                self._inbuff = self._inbuff[pos:]
                return target, READ, data
            elif len(self._inbuff) >= max_bytes:
                self._task = None
                data = self._inbuff[:max_bytes]
                self._inbuff = self._inbuff[max_bytes:]
                return target, READ, data
        return None

    def setup_read_until(self, target, delimiter, max_bytes):
        self.running = READ
        self._task = partial(self.check_read_until,
                             target, delimiter, max_bytes)

    def check_write(self, target, result):
        if self._exc is not None:
            self._task = None
            exc, self._exc = self._exc, None
            return target, ERROR, exc
        elif len(self._outbuff) == 0:
            self._task = None
            return target, WRITE, result
        return None

    def setup_write(self, target, result):
        self.running = WRITE
        self._task = partial(self.check_write, target, result)

    def reset_task(self):
        """ Resets buffer task. """
        self._task = None

    def check_task(self):
        """ Checks buffer task it can be done or not.
        (target, event, payload)
        """
        return self._task() if self._task is not None else None

    def write(self, data):
        """ Writes data to outgoing buffers. Return number of written bytes.
        """
        can_write = self._max_size - len(self._outbuff)
        can_write = len(data) if can_write > len(data) else can_write
        self._outbuff += data[:can_write]
        return can_write

    def close(self):
        """ Closes this.
        """
        if self._active:
            self._active = False
            dispatcher.release_watching(self)
            if self._socket:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except IOError:
                    pass
                finally:
                    self._socket.close()
