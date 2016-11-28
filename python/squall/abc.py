from abc import ABCMeta, abstractmethod


class EventLoop(metaclass=ABCMeta):
    """ Abstract base class of event loop.
    """

    @property
    @abstractmethod
    def READ(cls):
        """ Event code "I/O device redy to read".
        This is must be class property!
        """

    @property
    @abstractmethod
    def WRITE(cls):
        """ Event code "I/O device redy to write".
        This is must be class property!
        """

    @property
    @abstractmethod
    def ERROR(cls):
        """ Event code "Event loop internal error".
        This is must be class property!
        """

    @property
    @abstractmethod
    def TIMEOUT(cls):
        """ Event code "Timeout expired".
        This is must be class property!
        """

    @property
    @abstractmethod
    def SIGNAL(cls):
        """ Event code "System signal received".
        This is must be class property!
        """

    @property
    @abstractmethod
    def CLEANUP(cls):
        """ Event code "Event dispatching has terminated".
        This is must be class property!
        """

    @classmethod
    @abstractmethod
    def instance(cls):
        """ Returns thread local instance.
        """

    @property
    @abstractmethod
    def running(self):
        """ Returns `True` if event loop is running.
        """

    @property
    @abstractmethod
    def pending(self):
        """ Number of the pending watchers.
        """

    @abstractmethod
    def start(self):
        """ Starts event loop.
        """

    @abstractmethod
    def stop(self):
        """ Stops event loop.
        """

    @abstractmethod
    def watch_timer(self, callback, ctx, seconds):
        """ Sets an event dispatcher to call `callback` for `ctx`
        with code `TIMEOUT` after a specified time in seconds.
        If success returns callable which cancels this watching
        at call otherwise `None`.
        """

    @abstractmethod
    def watch_io(self, callback, ctx, fd, events):
        """ Sets an event dispatcher to call `callback` for `ctx` 
        with code `READ` and/or `WRITE` when I/O device  with given
        `fd` will be ready for corresponding I/O operations.
        If success returns callable which cancels this watching
        at call otherwise `None`.
        """

    @abstractmethod
    def watch_signal(self, callback, ctx, signum):
        """ Sets an event dispatcher to call `callback` for `ctx`  
        with code `SIGNAL` when a systems signal with given `signum`
        will be received.
        If success returns callable which cancels this watching
        at call otherwise `None`.
        """


class EventDispatcher(metaclass=ABCMeta):
    """ Abstract base class of event dispatcher

    This is designed for use with a callback functions. The watching
    setup functions (`watch_*`) can be used for one callback together.
    But if callback returns `False` all watching (all, not only triggered)
    will be canceled. Calling the same a watching setup function for the
    second time cancels the settings made in the first call.

    Event dispatcher should be not initialized (bind with event loop) in
    constructor, do it at start.
    """

    @property
    @abstractmethod
    def running(self):
        """ Returns `True` if event dispatcher is running.
        """

    @abstractmethod
    def start(self):
        """ Starts event dispatcher.
        """

    @abstractmethod
    def stop(self):
        """ Stops event dispatcher.
        """

    @abstractmethod
    def watch_timer(self, callback, seconds):
        """ Sets an event dispatcher to call `callback` with code `TIMEOUT`
        after a specified time in seconds.
        """

    @abstractmethod
    def watch_io(self, callback, fd, events):
        """ Sets an event dispatcher to call `callback` with code `READ`
        and/or `WRITE` when I/O device  with given `fd` will be ready
        for corresponding I/O operations.
        """

    @abstractmethod
    def watch_signal(self, callback, signum):
        """ Sets an event dispatcher to call `callback` with code `SIGNAL`
        when a systems signal with given `signum` will be received.
        """

    @abstractmethod
    def cancel(self, callback):
        """ Cancels all watchings for a given `callback`.
        """


class AutoBuffer(metaclass=ABCMeta):
    """ Event-driven read-write I/O autobuffer.
    """

    @property
    @abstractmethod
    def block_size(self):
        """ The block size of data reads / writes to the I/O device at once.
        must be int(block_size / 64) == block_size / 64
        and strongly recommended block_size <= 64 * 1024
        """

    @property
    @abstractmethod
    def max_size(self):
        """ Maximum size of the incoming / outcoming data buffers.
        must be int(max_size / block_size) == max_size / block_size
        """

    @property
    @abstractmethod
    def last_error(self):
        """ Returns last occurred error.
        """

    @property
    @abstractmethod
    def closed(self):
        """ Returns `True` if this is released.
        """

    @abstractmethod
    def watch_read_bytes(self, callback, number):
        """ Sets an autobuffer to call `callback` with code `READ`
        and result as block of bytes when autobuffer received given
        `number` of bytes.
        """

    @abstractmethod
    def watch_read_until(self, callback, delimiter, max_number):
        """ Sets an autobuffer to call `callback` with code `READ`
        and result as block of bytes when autobuffer received given
        `delimiter` or `number` of bytes, `delimiter` would be
        included in result.
        """

    @abstractmethod
    def watch_flush(self, callback):
        """ Sets an autobuffer to call `callback` with code `WRITE`
        when a autobuffer will complete drain outcoming buffer.
        """

    @abstractmethod
    def write(self, data):
        """ Puts `data` bytes to outcoming buffer to asynchronous
        sending. Returns the number of bytes written.
        """

    @abstractmethod
    def cancel(self):
        """ Cancels all watchings.
        """

    @abstractmethod
    def release(self):
        """ Cancels all watchings and destroys internal buffers.
        """
