""" Interfaces of classes `squall.core`
"""
import sys
from concurrent.futures import Future
from abc import ABCMeta, abstractmethod
from typing import Tuple, Union, Any
from collections.abc import Awaitable, Callable


class Coroutine(metaclass=ABCMeta):
    """ Future-like coroutine with a mostly-compatible
    `concurrent.futures.Future` what produced with call
    `Dispatcher.submit`.
    """

    @abstractmethod
    def running(self) -> bool:
        """ Returns True if this coroutine is currently running.
        """

    @abstractmethod
    def cancelled(self) -> bool:
        """ Returns True if this coroutine has been cancelled.
        """

    @abstractmethod
    def done(self) -> bool:
        """ Returns True if this coroutine has finished with result.
        """

    @abstractmethod
    def result(self) -> Any:
        """ If this coroutine has finished succeeded returns its result
        or raises exception otherwise. If a result isn’t yet available,
        raises NotImplementedError. Use `Dispatcher.complete` to get result
        asynchronously.
        """

    @abstractmethod
    def exception(self) -> None:
        """ If this coroutine has fail, returns exception or `None` in otherwise.
        If a result isn’t yet available, raises NotImplementedError.
        Use `Dispatcher.complete` to get result asynchronously.
        """

    @classmethod
    @abstractmethod
    def current(cls) -> 'Coroutine':
        """ Return current coroutine.
        """

    @abstractmethod
    def switch(self, value: Any):
        """ Sends some value into coroutine to switches its running back.
        """

    @abstractmethod
    def add_done_callback(self, callback: [['Coroutine'], None]) -> None:
        """ Attaches the given `callback` to this coroutine.
        """

    @abstractmethod
    def cancel(self) -> bool:
        """ Cancel this coroutine.
        """


class Dispatcher(metaclass=ABCMeta):
    """ Coroutine switcher/dispatcher
    """

    @abstractmethod
    def __init__():
        """ Constructor
        """

    @property
    @abstractmethod
    def READ(self) -> int:
        """ Event code I/O ready to read.
        """

    @property
    @abstractmethod
    def WRITE(self) -> int:
        """ Event code I/O ready to write.
        """

    @abstractmethod
    def submit(self, corofunc: Callable, *args, **kwargs) -> Coroutine:
        """ Creates the coroutine and submits to execute.
        """

    @abstractmethod
    def start(self):
        """ Starts the coroutine dispatching.
        """

    @abstractmethod
    def stop(self):
        """ Stops a coroutine dispatching
        """

    @abstractmethod
    def sleep(self, seconds: float = None) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        after `seconds` or at next loop if `seconds` is `None`.
        """

    @abstractmethod
    def ready(self, fd: int, mode: int, *, timeout: float = None) -> Awaitable:
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
    def complete(self, *futures: Tuple[Union[Coroutine, Future]],
                 timeout: float = None) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        when the given future-like or list of future-like objects has done.

        Raises:
            TimeoutError: `timeout` is set and elapsed.
        """


class IOStream(metaclass=ABCMeta):
    """ Base async I/O stream. With used in stream hanslers.
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
    def read_until(self, delimiter: bytes,
                   *, max_bytes: int = None, timeout: float = None) -> Awaitable:
        """ Returns awaitable to asynchronously read until we have found the given
        delimiter. The result includes all the data read including the delimiter.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            LookupError: when delimiter not found but buffer size is equal or greater `max_bytes`.
            IOError: occurred any I/O error.
        """

    @abstractmethod
    def read_exactly(self, num_bytes: int, *, timeout: float = None) -> Awaitable:
        """ Returns awaitable to asynchronously read a number of bytes.

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
    def flush(self, *, timeout: float = None) -> Awaitable:
        """ Returns awaitable to asynchronously drain an outcoming buffer of this stream.

        Raises:
            TimeoutError: `timeout` is defined and elapsed.
            IOError: occurred any I/O error.
        """

    @abstractmethod
    def close(self) -> None:
        """ Closes stream and associated resources.
        """


if sys.version_info[:2] > (3, 5):
    StreamHandler = Callable[[Dispatcher, IOStream, str], Coroutine]
else:
    StreamHandler = Callable


class TCPServer(metaclass=ABCMeta):
    """ Asynchronous TCP server
    """

    @abstractmethod
    def __init__(self, stream_handler: StreamHandler,
                 block_size: int = 1024, buffer_size: int = 65536):
        """ Constructor
        """

    @property
    @abstractmethod
    def active(self) -> bool:
        """ Returns `True` if this server is active (not stopped).
        """

    @abstractmethod
    def bind(self, port: int, address: str = None,
             *, backlog: int = 128, reuse_port: bool = False) -> None:
        """ Binds this server to the given port on the given address.
        """

    @abstractmethod
    def unbind(self, port: int, address: str = None) -> None:
        """ Unbinds this server from the given port on the given address.
        """

    @abstractmethod
    def before_start(self, disp: Dispatcher) -> None:
        """ Called before starting this server.

        May be overridden to initialize and start other coroutines there.
        """

    @abstractmethod
    def start(self, num_processes: int = 1) -> None:
        """ Starts this server.
        """

    @abstractmethod
    def stop(self) -> None:
        """ Stops this server.
        """
