""" Abstract base classes (Interfaces)
"""
from abc import ABCMeta, abstractmethod
try:
    from typing import Coroutine, Awaitable
except ImportError:
    from collections.abc import Coroutine, Awaitable



class Switcher(metaclass=ABCMeta):
    """ Abstract base class of the coroutine switcher
    """

    @property
    @abstractmethod
    def current(self) -> Coroutine:
        """ Running coroutine """

    @abstractmethod
    def switch(self, coro: Coroutine, value) -> bool:
        """ Sends some value into coroutine to switches its running back.
        Returns `True` if coroutine is continue running and `False` if has finished.
        """


class Dispatcher(Switcher):
    """ Abstract base class of the coroutine dispatcher/switcher
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
    def spawn(self, corofunc, *args, **kwargs) -> Coroutine:
        """ Creates and starts coroutine.
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
        It will raise `TimeoutError` if `timeout` is set and elapsed.
        """

    @abstractmethod
    def signal(self, signum: int) -> Awaitable:
        """ Returns the awaitable that switches current coroutine back
        when received the system signal with a given `signum`.
        """
