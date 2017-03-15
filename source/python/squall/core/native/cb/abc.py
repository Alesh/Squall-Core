""" Abstract base classes (Interfaces)
"""
from abc import ABCMeta, abstractmethod
from socket import SocketType
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


class AutoBuffer(metaclass=ABCMeta):
    """ Abstract base class of the auto I/O buffer
    """

    @property
    @abstractmethod
    def READ(self) -> int:
        """ Event code "I/O device ready to read". """

    @property
    @abstractmethod
    def WRITE(self) -> int:
        """ Event code "I/O device ready to write". """

    @property
    @abstractmethod
    def active(self) -> bool:
        """ Returns `True` if this is active (not closed). """

    @property
    @abstractmethod
    def block_size(self) -> int:
        """ Size of block of data reads/writes to the I/O device at once. """

    @property
    @abstractmethod
    def buffer_size(self) -> int:
        """ Maximum size of the read/write buffers. """

    @abstractmethod
    def setup_task(self, callback: Callable[[Any], None], trigger_event: int,
                   task_method: Callable[[Any], Any], timeout: float) -> Any:
        """ Calls `task_method` if return a result if it not `None`.
        Otherwise configures an execution of `task_method` at time after a
        `trigger_event` and a call of `callback` if `task_method` return not `None`.
        Returns directly or via `callback` TimeoutError if `timeout` is defined and elapsed.
        """

    @abstractmethod
    def cancel_task(self):
        """ Cancels callback which was setup with `AutoBuffer.setup_task`.
        """

    @abstractmethod
    def read(self, max_bytes: int) -> bytes:
        """ Read bytes from incoming buffer how much is there, but not more max_bytes.
        """

    @abstractmethod
    def write(self, data: bytes) -> int:
        """ Writes data to the outcoming buffer.
        Returns number of bytes what has been written.
        """

    @abstractmethod
    def close(self):
        """ Closes this and associated resources.
        """


class SocketAcceptor(metaclass=ABCMeta):
    """ Abstract base class of the auto I/O buffer
    """

    @abstractmethod
    def __init__(self, event_loop: EventLoop, socket_: SocketType,
                 on_accept: Callable[[SocketType, str], None]):
        """ Constructor """

    @abstractmethod
    def close(self):
        """ Closes this and associated resources.
        """
