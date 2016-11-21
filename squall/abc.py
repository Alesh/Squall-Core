"""
Abstract base classes and interfaces.
"""
from abc import ABCMeta, abstractmethod


class EventDispatcher(metaclass=ABCMeta):
    """ Event dispatcher designed for use with a callback functions.

    Important details of implementation watching up (`watch_timer`.
    `watch_io`. `watch_signal`) functions.

    * If `callback` returns `True` watching will be resumed otherwise no.
    * Watching up functions can be used for one callback together, but
      if `once` flag set to `True` all watching will be canceled before
      call `callback`.
    * Calling the same function for the second time cancels the settings
      made in the first call.
    """

    @property
    @abstractmethod
    def READ(self):
        """ Event code "I/O device redy to read".
        """

    @property
    @abstractmethod
    def WRITE(self):
        """ Event code "I/O device redy to write".
        """

    @property
    @abstractmethod
    def ERROR(self):
        """ Event code "Event dispatcher internal error"..
        """

    @property
    @abstractmethod
    def TIMEOUT(self):
        """ Event code "Timeout expired".
        """

    @property
    @abstractmethod
    def SIGNAL(self):
        """ Event code "System signal received".
        """

    @property
    @abstractmethod
    def CLEANUP(self):
        """ Event code "Event dispatcher has terminated".
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
