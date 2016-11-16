"""
Abstract base classes.
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
    def watch_timer(self, callback, seconds, once=False):
        """ Sets an event dispatcher to call `callback` with code `TIMEOUT`
        after a specified time in seconds.
        """

    @abstractmethod
    def watch_io(self, callback, fd, events, once=False):
        """ Sets an event dispatcher to call `callback` with code `READ`
        and/or `WRITE` when I/O device  with given `fd` will be ready
        for corresponding I/O operations.
        """

    @abstractmethod
    def watch_signal(self, callback, signum, once=False):
        """ Sets an event dispatcher to call `callback` with code `SIGNAL`
        when a systems signal with given `signum` will be received.
        """

    @abstractmethod
    def cancel(self, callback):
        """ Cancels all watchings for a given `callback`.
        """
