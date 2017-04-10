""" Internal interfaces
"""
import sys
from squall.core.abc import ABCMeta, abstractmethod, Callable, Any

if sys.version_info[:2] > (3, 5):
    Callback = Callable[[Any], None]
    TaskMethod = Callable[[Any], Any]
else:
    Callback = Callable
    TaskMethod = Callable


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
    def setup_timer(self, callback: Callback, seconds: float) -> Any:
        """ Setup to run the `callback` after a given `seconds` elapsed.
        Returns handle for using with `EventLoop.cancel_timer`
        """

    @abstractmethod
    def cancel_timer(self, handle: Any):
        """ Cancels callback which was setup with `EventLoop.setup_timer`.
        """

    @abstractmethod
    def setup_io(self, callback: Callback, fd: int, events: int):
        """ Setup to run the `callback` when I/O device with
        given `fd` would be ready to read or/and write.
        Returns handle for using with `EventLoop.update_io` and `EventLoop.cancel_io`
        """

    @abstractmethod
    def update_io(self, handle: Any, events: int):
        """ Updates call settings for callback which was setup with `EventLoop.setup_io`.
        """

    @abstractmethod
    def cancel_io(self, handle: Any):
        """ Cancels callback which was setup with `EventLoop.setup_io`.
        """

    @abstractmethod
    def setup_signal(self, callback: Callback, signum: int):
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

    # @abstractmethod
    # def setup_task(self, callback: Callback, trigger_event: int,
    #                task_method: TaskMethod, timeout: float) -> Any:
    #     """ Calls `task_method` if return a result if it not `None`.
    #     Otherwise configures an execution of `task_method` at time after a
    #     `trigger_event` and a call of `callback` if `task_method` return not `None`.
    #     Returns directly or via `callback` TimeoutError if `timeout` is defined and elapsed.
    #     """

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
