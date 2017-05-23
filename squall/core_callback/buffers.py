""" Buffers
"""
import errno
from squall.core_callback.eventloop import EventLoop


class _Buffer(object):
    """ Base class for buffers
    """
    def __init__(self, block_size, max_size):
        self.block_size = block_size
        self.max_size = max_size
        self._threshold = -1
        self._buff = b''

    @property
    def size(self):
        """ Current buffer size """
        return len(self._buff)

    def cancel(self):
        """ Resets buffer task """
        self._threshold = -1

    def cleanup(self):
        """ Cleanups buffer. """
        self.cancel()
        self._buff = b''


class OutBuffer(_Buffer):
    """ Outcoming buffer
    """
    def __init__(self, transmiter, block_size, max_size):
        self._transmiter = transmiter
        super().__init__(block_size, max_size)

    def __call__(self, event):
        """ Do buffer job

        Returns:
            (tuple): tuple containing:
                pause (bool): `True` if buffer empty
                result (int): 1 if buffer size less or equal than threshold otherwise 0
                errno (int) last errno got on receiving data otherwise 0
        """
        result = error = 0
        if event & EventLoop.ERROR:
            error = errno.EIO
        elif event == 0 or event & EventLoop.WRITE:
            if event & EventLoop.WRITE:
                number = self.block_size if self.block_size < self.size else self.size
                if number > 0:
                    sent, error = self._transmiter(self._buff[:number])
                    if sent > 0:
                        self._buff = self._buff[sent:]
            if self._threshold >= 0:
                result = int(self.size <= self._threshold)
        pause = (self.size == 0)
        return result, pause, error

    def setup(self, threshold):
        """ Sets up a flushing `threshold`.

        Returns:
            (tuple): tuple containing:
                pause (bool): `True` if buffer empty
                result (int): 1 if buffer size less or equal than threshold otherwise 0
        """
        self._threshold = threshold if threshold > 0 else 0
        if self._threshold > self.max_size - self.block_size:
            self._threshold = self.max_size - self.block_size
        result, _, _ = self(0)
        return result

    def write(self, data):
        """ Writes bytes `data` to the outcoming buffer.

        Returns:
            int: number of written bytes.
        """
        number = len(data)
        if number > self.max_size - self.size:
            number = self.max_size - self.size
        if number > 0:
            self._buff += data[:number]
        return number if number > 0 else 0


class InBuffer(_Buffer):
    """ Incoming buffer
    """
    def __init__(self, receiver, block_size, max_size):
        self._delimiter = None
        self._receiver = receiver
        super().__init__(block_size, max_size)

    def __call__(self, event):
        """ Do buffer job

        Returns:
            (tuple): tuple containing:
                pause (bool): `True` if buffer full
                result (int): positive number of ready to read data otherwise
                              0 if nothing to read or
                              -1 if `delimiter` not found but threshold reached
                errno (int) last errno got on receiving data otherwise 0
        """
        result = error = 0
        if event & EventLoop.ERROR:
            error = errno.EIO
        elif event == 0 or event & EventLoop.READ:
            if event & EventLoop.READ:
                number = self.max_size - self.size
                if number > self.block_size:
                    number = self.block_size
                if number > 0:
                    data, error = self._receiver(number)
                    if data:
                        self._buff += data
            if self._threshold >= 0:
                if self._delimiter:
                    pos = self._buff.find(self._delimiter)
                    if pos >= 0:
                        result = pos + len(self._delimiter)
                    elif self._threshold <= self.size:
                        result = -1
                elif self._threshold <= self.size:
                    result = self._threshold
        pause = (self.size >= self.max_size)
        return result, pause, error

    def setup(self, threshold=0, delimiter=None):
        """ Sets up a reading `threshold` and `delimiter`. """
        self._delimiter = delimiter
        self._threshold = (self.max_size
                           if threshold <= 0 or threshold > self.max_size
                           else threshold)
        result, _, _ = self(0)
        return result

    def read(self, number):
        """ Read bytes from incoming buffer how much is there, but not more `number`.

        Return:
            bytes: result
        """
        number = self.size if number <= 0 or number > self.size else number
        if number > 0:
            result, self._buff = self._buff[:number], self._buff[number:]
            return result
        return b''
