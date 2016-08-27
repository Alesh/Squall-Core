""" Failback I/O autobuffer classes.
"""
import errno
from functools import partial

from .dispatcher import Dispatcher
READ = Dispatcher.READ
WRITE = Dispatcher.WRITE
ERROR = Dispatcher.ERROR
TIMER = Dispatcher.TIMER
CLEANUP = Dispatcher.CLEANUP


class StreamAutoBuffer(object):

    """ Socket stream auto buffer.
    """

    def __init__(self, socket_, chunk_size, max_size, dispatcher=None):
        self._mask = 0
        self._errno = 0
        self._task = None
        self._incoming = b''
        self._outcoming = b''
        self._socket = socket_
        self._fd = socket_.fileno()
        self._max_size = max_size
        self._chunk_size = chunk_size
        self._disp = dispatcher or Dispatcher.current()
        if self._disp.watch_io(self, self._fd, self._mask | READ):
            self._mask = self._mask | READ

    def _on_timeout(self, revent, payload):
        self._disp.release_watching(self._on_timeout)
        if revent & TIMER:
            revent = ERROR
            payload = errno.ETIMEDOUT
        self(revent, payload)
        return False

    def __call__(self, revent, payload):
        if revent & (ERROR | CLEANUP):
            if revent & ERROR:
                self._errno = errno.EIO if payload is None else payload
            else:
                self._errno = errno.EHOSTDOWN
        else:
            try:
                if revent & READ:
                    data = self._socket.recv(self._chunk_size)
                    if len(data) > 0:
                        self._incoming += data
                        if len(self._incoming) >= self._max_size:
                            mask = self._mask ^ READ
                            if (self._mask & READ and
                               self._disp.watch_io(self, self._fd, mask)):
                                self._mask = mask
                            else:
                                self._errno == errno.EBUSY
                    else:
                        raise IOError(errno.ECONNRESET, "")
                if revent & WRITE:
                    if len(self._outcoming) > 0:
                        chunk = self._outcoming[:self._chunk_size]
                        sent = self._socket.send(chunk)
                        if sent > 0:
                            self._outcoming = self._outcoming[sent:]
                            if len(self._outcoming) == 0:
                                mask = self._mask ^ WRITE
                                if (self._mask & WRITE and
                                   self._disp.watch_io(self,
                                                            self._fd, mask)):
                                    self._mask = mask
                                else:
                                    self._errno == errno.EBUSY
                        else:
                            raise IOError(errno.ECOMM, "")
            except IOError as exc:
                self._errno = exc.errno or errno.EIO

        if self._task is not None:
            callback, event, check_done = self._task
            if self._errno == 0:
                try:
                    result = check_done()
                except OSError as exc:
                    self._errno = exc.errno
            if self._errno != 0:
                event = ERROR
                result = self._errno
            if result:
                self.reset()
                callback(event, result)
        return True

    @property
    def chunk_size(self):
        return self._chunk_size

    @property
    def max_size(self):
        return self._max_size

    @property
    def outfilling(self):
        return len(self._outcoming) / self._max_size

    def read_bytes(self, num_bytes):
        result = None
        if len(self._incoming) >= num_bytes:
            result, self._incoming = (self._incoming[:num_bytes],
                                      self._incoming[num_bytes:])
        if result is not None and not (self._mask & READ):
            if self._disp.watch_io(self, self._fd, self._mask | READ):
                self._mask = self._mask | READ
        return result

    def setup_read_bytes(self, callback, num_bytes, timeout):
        if self._task is None:
            if (self._mask & READ or len(self._incoming) >= self._max_size or
               self._disp.watch_io(self, self._fd, self._mask | READ)):
                self._mask = self._mask | READ
                self._task = (callback, READ,
                              partial(self.read_bytes, num_bytes))
                if timeout > 0:
                    self._disp.watch_timer(self._on_timeout, timeout)
            return True
        return False

    def read_until(self, delimiter, max_bytes):
        result = None
        if len(delimiter):
            pos = self._incoming.find(delimiter)
            if pos >= 0:
                pos += len(delimiter)
                result = self._incoming[:pos]
                self._incoming = self._incoming[pos:]
            elif len(self._incoming) >= max_bytes:
                raise IOError(errno.ENOBUFS, "").errno
        if result is not None and not (self._mask & READ):
            if self._disp.watch_io(self, self._fd, self._mask | READ):
                self._mask = self._mask | READ
        return result

    def setup_read_until(self, callback, delimiter, max_bytes, timeout):
        if self._task is None:
            if (self._mask & READ or len(self._incoming) >= self._max_size or
               self._disp.watch_io(self, self._fd, self._mask | READ)):
                self._mask = self._mask | READ
                self._task = (callback, READ,
                              partial(self.read_until, delimiter, max_bytes))
                if timeout > 0:
                    self._disp.watch_timer(self._on_timeout, timeout)
            return True
        return False

    def flush(self):
        if len(self._outcoming) == 0:
            return True
        return False

    def setup_flush(self, callback, timeout):
        if self._task is None:
            if (self._mask & WRITE or
               self._disp.watch_io(self, self._fd, self._mask | WRITE)):
                self._mask = self._mask | WRITE
                self._task = (callback, WRITE, self.flush)
                if timeout > 0:
                    self._disp.watch_timer(self._on_timeout, timeout)
                return True
        return False

    def write(self, data):
        chunk = data[:self._max_size - len(self._outcoming)]
        self._outcoming += chunk
        return len(chunk)

    def reset(self):
        self._disp.disable_watching(self._on_timeout)
        self._task = None
        self._errno = 0

    def cleanup(self):
        self._incoming = b''
        self._outcoming = b''
        self._disp.release_watching(self)
        self._disp.release_watching(self._on_timeout)
