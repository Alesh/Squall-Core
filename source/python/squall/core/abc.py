""" External interfaces
"""
import sys
from abc import ABCMeta, abstractmethod

try:
    from typing import Coroutine, Awaitable, Callable
except ImportError:
    from collections.abc import Coroutine, Awaitable, Callable
from typing import Tuple, Optional, Any


class Future(metaclass=ABCMeta):
    """ Interface of future-like objects
    """

    @abstractmethod
    def cancel(self):
        """ Cancel the future if possible.

        See also:
            `concurrent.futures.Future.cancel`
        """

    @abstractmethod
    def cancelled(self) -> bool:
        """ Return True if the future was cancelled.

        See also:
            `concurrent.futures.Future.cancel`
        """

    @abstractmethod
    def running(self) -> bool:
        """ Return True if the future is currently executing.

        See also:
            `concurrent.futures.Future.running`
        """

    @abstractmethod
    def done(self) -> bool:
        """ Return True of the future was cancelled or finished executing.

        See also:
            `concurrent.futures.Future.done`
        """

    @abstractmethod
    def add_done_callback(self, callback):
        """ Attaches a callable that will be called when the future finishes.

        See also:
            `concurrent.futures.Future.add_done_callback`
        """

    @abstractmethod
    def result(self) -> Any:
        """ Return the result of the call that the future represents.

        See also:
            `concurrent.futures.Future.result`
        """

    @abstractmethod
    def exception(self) -> BaseException:
        """ Return the exception raised by the call that the future represents.

        See also:
            `concurrent.futures.Future.exception`
        """

    @classmethod
    def __subclasshook__(cls, C):
        if cls is Future:
            for name in cls.__abstractmethods__:
                if not any(name in B.__dict__ for B in C.__mro__):
                    return False
            return True
        return NotImplemented


class Dispatcher(metaclass=ABCMeta):
    """ Interface of the coroutine dispatcher/switcher
    """

    @property
    @abstractmethod
    def READ(self) -> int:
        """ Event code "I/O device ready to read".
        """

    @property
    @abstractmethod
    def WRITE(self) -> int:
        """ Event code "I/O device ready to write".
        """

    @abstractmethod
    def submit(self, corofunc, *args, **kwargs) -> Future:
        """ Creates and return coroutine wrapped as future-like.

        Warning:
            Do not directly call `send`, `throw`, 'close' for coroutines returned by this method.
        """

    @abstractmethod
    def switch(self, coro: Coroutine, value) -> Tuple[Optional[Any], Optional[Exception]]:
        """ Sends some value into coroutine to switches its running back.

        Returns:
             * (None, None) if it's continue running
             * (Any, StopIteration) if it's finished
             * (None, GeneratorExit) if it's closed.
             * (None, Exception) if it's aborted by uncaught exception.
        """

    @abstractmethod
    def start(self):
        """ Starts the coroutine dispatching.
        """

    @abstractmethod
    def stop(self):
        """ Stops a coroutine dispatching"""

    @abstractmethod
    def sleep(self, seconds: float = None) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        after `seconds` or at next loop if `seconds` is `None`.
        """

    @abstractmethod
    def ready(self, fd: int, events: int, *, timeout: float = None) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        when I/O device with a given `fd` ready to read and/or write.

        Raises:
            TimeoutError: if `timeout` is set and elapsed.
        """

    @abstractmethod
    def signal(self, signum: int) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        when received the system signal with a given `signum`.
        """

    @abstractmethod
    def complete(self, *futures: Tuple[Future], timeout: float = None) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        when the given future or list of futures has done.

        Raises:
            TimeoutError: `timeout` is set and elapsed.
        """


class IOStream(metaclass=ABCMeta):
    """ Interface of the async I/O stream
    """

    @property
    @abstractmethod
    def active(self) -> bool:
        """ Returns `True` if this stream is active (not closed).
        """

    @property
    @abstractmethod
    def block_size(self) -> int:
        """ Size of block of data reads/writes to the I/O device at once.
        """

    @property
    @abstractmethod
    def buffer_size(self) -> int:
        """ Maximum size of the read/write buffers.
        """

    @abstractmethod
    def read(self, max_bytes: int) -> bytes:
        """ Read bytes from incoming buffer how much is there, but not more max_bytes.
        """

    @abstractmethod
    def read_exactly(self, num_bytes: int, *, timeout: float = None) -> Awaitable:
        """ Asynchronously read a number of bytes.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """

    @abstractmethod
    def read_until(self, delimiter: bytes, *, max_bytes: int = None, timeout: float = None) -> Awaitable:
        """ Asynchronously read until we have found the given delimiter.
        The result includes all the data read including the delimiter.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            BufferError: incomming buffer if full but delemiter not found.
            IOError: occurred any I/O error.
        """

    @abstractmethod
    def flush(self, *, timeout: float = None) -> Awaitable:
        """ Asynchronously drain an outcoming buffer of this stream.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """

    @abstractmethod
    def write(self, data: bytes) -> int:
        """ Writes data to the outcoming buffer of this stream.

        Returns:
            number of bytes what has been written.
        """

    @abstractmethod
    def close(self):
        """ Closes stream and associated resources.
        """


if sys.version_info[:2] > (3, 5):
    StreamHandler = Callable[[Dispatcher, IOStream, str], Coroutine]
else:
    StreamHandler = Callable


class TCPServer(metaclass=ABCMeta):
    """ Interface of the async TCP Server
    """

    @abstractmethod
    def __init__(self, stream_handler: StreamHandler,
                 block_size: int = 1024, buffer_size: int = 64 * 1024):
        """ Constructor """

    @property
    @abstractmethod
    def active(self) -> bool:
        """ Returns `True` if this server is active (not stopped).
        """

    @abstractmethod
    def bind(self, port: int, address: str = None, *, backlog: int = 128, reuse_port: bool = False):
        """ Binds this server to the given port on the given address.
        """

    @abstractmethod
    def unbind(self, port: int, address: str = None):
        """ Unbinds this server from the given port on the given address.
        """

    @abstractmethod
    def before_start(self, disp: Dispatcher):
        """ Called before starting this server.

        May be overridden to initialize and start other coroutines there.
        """

    @abstractmethod
    def start(self, num_processes: int = 1):
        """ Starts this server.
        """

    @abstractmethod
    def stop(self):
        """ Stops this server.
        """


class TCPClient(metaclass=ABCMeta):
    """ Interface of the async TCP Client
    """

    @abstractmethod
    def __init__(self, disp: Dispatcher, block_size: int = 1024, buffer_size: int = 64 * 1024):
        """ Constructor """

    @abstractmethod
    def connect(self, stream_handler: StreamHandler,
                host: str, port: int, *, timeout: float = None) -> Awaitable:
        """ Asynchronously connects to the given `host`:`port` if success create stream
        and process client connection into `stream_handler`.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """
