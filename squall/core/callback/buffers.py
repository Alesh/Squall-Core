""" Event-driven I/O buffers
"""

READ    = 0x00000001
WRITE   = 0x00000002
TIMEOUT = 0x00000004
SIGNAL  = 0x00000008
ERROR   = 0x00000010
CLEANUP = 0x00000020
BUFFER  = 0x00000040


class OutcomingBuffer(object):
    """ Outcoming I/O buffer
    """

    def __init__(self, transmiter, resumer, block_size, max_size):
        assert callable(transmiter)
        assert block_size < max_size and (block_size % 8) == 0 and (max_size % block_size) == 0
        self._on_event = None  # lambda revents, payload=None: None
        self._pause = lambda: resumer(False)
        self._transmiter = transmiter
        self._block_size = block_size
        self._max_size = max_size
        self._threshold = 0
        self._mode = WRITE
        self._buff = b''

    def __call__(self, revents):
        """ Event handler """
        if revents & (self._mode | ERROR):
            error = 0
            payload = None
            if revents == self._mode:
                number = self.size
                if self._block_size < number:
                    number = self._block_size
                if number > 0:
                    sent, error = self._transmiter(self._buff[:number])
                    if sent > 0:
                        self._buff = self._buff[sent:]
                    else:
                        revents = BUFFER | ERROR
            if revents & ERROR or self.size == 0:
                self._pause()
            if self._on_event:
                on_event = self._on_event
                if not revents & ERROR:
                    if self.result > 0:
                        revents = BUFFER | WRITE
                if revents & ERROR:
                    self.cancel()
                    payload = error
                if revents != 0:
                    on_event(revents, payload)

    @property
    def size(self):
        """ Current buffer size """
        return len(self._buff)

    @property
    def result(self):
        """ Calculated buffer task result. """
        if self._on_event is not None and self.size <= self._threshold:
            return 1
        return 0

    def setup(self, on_event, threshold):
        """ Setup buffer task. """
        self.cancel()  # Cancel previos buffer task
        if threshold > self._max_size - self._block_size:
            threshold = self._max_size - self._block_size
        #  setup new buffer task
        self._threshold = threshold
        self._on_event = on_event
        return self.result

    def cancel(self):
        """ Cancels buffer task. """
        self._on_event = None
        self._threshold = 0

    def write(self, data):
        """ Writes data to the outcoming buffer. Returns number of written bytes.
        """
        number = self._max_size - self.size
        if len(data) < number:
            number = len(data)
        if number > 0:
            self._buff += data[:number]
        return number

    def cleanup(self):
        self._buff = b''
        self.cancel()


class IncomingBuffer(object):
    """ Incoming I/O buffer
    """

    def __init__(self, receiver, resumer, block_size, max_size):
        assert callable(receiver)
        assert block_size < max_size and (block_size % 8) == 0 and (max_size % block_size) == 0
        self._on_event = None  # lambda revents, payload=None: None
        self._pause = lambda: resumer(False)
        self._receiver = receiver
        self._block_size = block_size
        self._max_size = max_size
        self._delimiter = None
        self._threshold = 0
        self._mode = READ
        self._buff = b''

    def __call__(self, revents):
        if revents & (self._mode | ERROR):
            error = 0
            payload = None
            if revents == self._mode:
                number = self._max_size - self.size
                if number > self._block_size:
                    number = self._block_size
                data, error = self._receiver(number)
                if data:
                    self._buff += data
                else:
                    revents = BUFFER | ERROR
            if revents & ERROR or self.size >= self._max_size:
                self._pause()
            if self._on_event:
                on_event = self._on_event
                if not revents & ERROR:
                    payload = self.result
                    if payload > 0:
                        revents = BUFFER | READ
                    elif payload < 0:
                        revents = BUFFER | ERROR | READ
                if revents & ERROR:
                    self.cancel()
                    payload = error
                if revents != 0:
                    on_event(revents, payload)

    @property
    def size(self):
        """ Current buffer size """
        return len(self._buff)

    @property
    def result(self):
        """ Calculated buffer task result. """
        if self._on_event is not None:
            if self._delimiter is not None:
                pos = self._buff.find(self._delimiter)
                if pos >= 0:
                    result = pos + len(self._delimiter)
                    return result if result < self._threshold else -1
                elif self.size >= self._threshold:
                    return -1
            elif self.size >= self._threshold:
                return self._threshold
        return 0

    def setup(self, on_event, delimiter, max_size):
        """ Setup buffer task. """
        self.cancel()  # Cancel previos buffer task
        max_size = max_size if max_size < self._max_size else max_size
        #  setup new buffer task
        self._delimiter = delimiter
        self._threshold = max_size
        self._on_event = on_event
        return self.result

    def cancel(self):
        """ Cancels buffer task. """
        self._delimiter = None
        self._on_event = None
        self._threshold = 0

    def read(self, number):
        """ Read bytes from incoming buffer how much is there, but not more `number`. """
        number = number if number < self.size else self.size
        if number > 0:
            self._buff, result = self._buff[number:], self._buff[:number]
            return result
        return b''

    def cleanup(self):
        self._buff = b''
        self.cancel()
