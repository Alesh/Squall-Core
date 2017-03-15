""" Abstract base classes (Interfaces)
"""
from abc import ABCMeta, abstractmethod
from typing import Any, Callable


class EventLoop(metaclass=ABCMeta):
    """ Callback based event dispatcher
    """

    @property
    @abstractmethod
    def READ(self) -> int:
        """ Event code "I/O device ready to read". """

    @property
    @abstractmethod
    def WRITE(self) -> int:
        """ Event code "I/O device ready to write". """

    @abstractmethod
    def start(self):
        """ Starts the event dispatching.
        """

    @abstractmethod
    def stop(self):
        """ Stops an event dispatching"""

    @abstractmethod
    def setup_timeout(self, callback: Callable[[Any], None],
                      seconds: float, result: Any = True) -> Any:
        """ Setup to run the `callback` after a given `seconds` elapsed.
        You can define parameter of `callback` to set `result`.
        Returns handle for using with `EventLoop.cancel_timeout`
        """

    @abstractmethod
    def cancel_timeout(self, handle: Any):
        """ Cancels callback which was setup with `EventLoop.setup_timeout`.
        """

    @abstractmethod
    def setup_ready(self, callback: Callable[[Any], None], fd: int, events: int):
        """ Setup to run the `callback` when I/O device with
        given `fd` would be ready to read or/and write.
        Returns handle for using with `EventLoop.cancel_ready`
        """

    @abstractmethod
    def cancel_ready(self, handle: Any):
        """ Cancels callback which was setup with `EventLoop.setup_ready`.
        """

    @abstractmethod
    def setup_signal(self, callback: Callable[[Any], None], signum: int):
        """ Setup to run the `callback` when system signal with a given `signum` received.
        Returns handle for using with `EventLoop.cancel_signal`
        """

    @abstractmethod
    def cancel_signal(self, handle: Any):
        """ Cancels callback which was setup with `EventLoop.setup_signal`.
        """
