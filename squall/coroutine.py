"""
Implementation of event-driven async/await coroutine switching.
"""
import os
import logging
import threading
from time import time
from functools import partial
from collections import deque

from squall import abc
from _squall import EventDispatcher

abc.EventDispatcher.register(EventDispatcher)

logger = logging.getLogger(__name__)


class Dispatcher(object):
    """ Event dispatcher designed for use with
    a **async/await** PEP492 coroutine and to switching them.
    """

    _tls = threading.local()

    def __init__(self):
        self._stack = deque()
        self._event_disp = EventDispatcher()

    class _LockAsCurrent(object):
        """ It provides the finding of the current coroutine.
        """
        def __init__(self, stack, coro):
            self._stack = stack
            self._coro = coro

        def __enter__(self):
            self._stack.appendleft(self._coro)
            return self

        def __exit__(self, exc_type, exc_value, exc_traceback):
            coro = self._stack.popleft()
            assert coro == self._coro
            if exc_type is not None:
                if exc_type not in (StopIteration, GeneratorExit):
                    logger.error("Coroutine %s closed"
                                 " due to uncaught exception", coro,
                                 exc_info=(exc_type, exc_value, exc_traceback))
                return True

    def _lock_as_current(self, coro):
        return self._LockAsCurrent(self._stack, coro)

    @classmethod
    def instance(cls):
        """ Returns default (thread local) instance.
        """
        if not hasattr(cls._tls, 'instance'):
            setattr(cls._tls, 'instance', cls())
        return getattr(cls._tls, 'instance')

    def start(self):
        """ Starts an event dispatcher and switching of coroutine..
        """
        self._event_disp.start()

    def stop(self):
        """ Stops it.
        """
        self._event_disp.stop()


class _Awaitable(object):
    """ Create awaitable objects which switches back by call..
    """
    def __init__(self, disp, cancel, setup, *args, **kwargs):
        self._ev = disp._event_disp
        self._coro = current(disp=disp)
        self._lock_as_current = disp._lock_as_current
        self._cancel = partial(cancel, self)
        self._has_timeout = 'timeout' in kwargs
        self._setup = partial(setup, self, *args, **kwargs)

    def __await__(self):
        if not self._setup():
            raise RuntimeError("Cannot setup event watching")
        try:
            event, payload = yield
            return payload if payload is not None else event
        except GeneratorExit:
            self._cancel()
            raise GeneratorExit

    def __call__(self, event, payload=None):
        with self._lock_as_current(self._coro):
            if not event & (self._ev.ERROR | self._ev.CLEANUP):
                if self._has_timeout and event & self._ev.TIMEOUT:
                    self._coro.throw(TimeoutError("I/O timed out"))
                else:
                    self._coro.send((event, payload))
            else:
                if event == self._ev.ERROR:
                    if payload is not None:
                        if isinstance(payload, Exception):
                            self._coro.throw(payload)
                        elif isinstance(payload, int):
                            exc = IOError(payload, os.strerror(payload))
                            self._coro.throw(exc)
                        else:
                            self._coro.throw(str(payload))
                    else:
                        self._coro.throw(IOError("Event loop internal error"))
                else:
                    self._cancel = lambda: None
                    self._coro.close()

READ = Dispatcher.instance()._event_disp.READ
WRITE = Dispatcher.instance()._event_disp.WRITE


class IOStream(object):
    """ Base class for async I/O streams.
    """

    def __init__(self, disp, autobuff):
        assert isinstance(disp, Dispatcher)
        assert isinstance(autobuff, abc.AutoBuffer)
        self._disp = disp
        self._event_disp = disp._event_disp
        self._autobuff = autobuff
        self._closed = False

    @property
    def closed(self):
        """ Returns `True` if this stream is closed.
        """
        return self._closed

    @property
    def block_size(self):
        """ The block size of data reads / writes to the I/O device at once.
        """
        return self._autobuff.block_size

    @property
    def buffer_size(self):
        """ Maximum size of the incoming / outcoming data buffers.
        """
        return self._autobuff.max_size

    def read_bytes(self, number, timeout=None):
        """ Returns awaitable which switch back when a autobuffer has
        given `number` of bytes or timeout exceeded if it set.
        Awaitable returns requested numbers of bytes
        or raises `TimeoutError` or `IOError`.
        """
        assert isinstance(number, int)
        number = (number
                  if number > 0 and number <= self.buffer_size
                  else self.buffer_size)
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))

        def cancel(callback):
            if timeout > 0:
                self._event_disp.cancel(callback)
            self._autobuff.cancel()

        def setup(callback, number, timeout):
            result = True
            if timeout > 0:
                result = self._event_disp.watch_timer(callback, timeout, True)
            if result:
                result = self._autobuff.watch_read_bytes(callback, number)
            if not result:
                cancel(callback)
            return result

        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(self._disp, cancel,
                          setup, number, timeout=timeout)

    def read_until(self, delimiter, max_number=None, timeout=None):
        """ Returns awaitable which switch back when a autobuffer has
        given `delimiter` or `max_number` of bytes or timeout exceeded
        if it set.
        Awaitable returns block of bytes ends with `delimiter` or
        `max_number` of bytes or raises `TimeoutError` or `IOError`.
        """
        assert isinstance(delimiter, bytes)
        assert isinstance(max_number, int)
        max_number = (max_number
                      if max_number > 0 and max_number <= self.buffer_size
                      else self.buffer_size)
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))

        def cancel(callback):
            if timeout > 0:
                self._event_disp.cancel(callback)
            self._autobuff.cancel()

        def setup(callback, delimiter, max_number, timeout):
            result = True
            if timeout > 0:
                result = self._event_disp.watch_timer(callback, timeout, True)
            if result:
                result = self._autobuff.watch_read_until(callback, delimiter,
                                                         max_number)
            if not result:
                cancel(callback)
            return result

        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(self._disp, cancel,
                          setup, delimiter, max_number, timeout=timeout)

    def flush(self, timeout=None):
        """ Returns awaitable which switch back when a autobuffer will
        complete drain outcoming buffer or timeout exceeded if it set.
        Awaitable returns insignificant value
        or raises `TimeoutError` or `IOError`.
        """
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))

        def cancel(callback):
            if timeout > 0:
                self._event_disp.cancel(callback)
            self._autobuff.cancel()

        def setup(callback, timeout):
            result = True
            if timeout > 0:
                result = self._event_disp.watch_timer(callback, timeout, True)
            if result:
                result = self._autobuff.watch_flush(callback)
            if not result:
                cancel(callback)
            return result

        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(self._disp, cancel,
                          setup, timeout=timeout)

    def write(self, data):
        """ Puts `data` bytes to outcoming buffer.
        """
        return self._autobuff.write(data)

    def close(self):
        """ Closes a strean and releases resourses.
        """
        self._closed = True
        self._autobuff.release()


def start():
    """ Starts default coroutine dispatcher.
    """
    Dispatcher.instance().start()


def stop():
    """ Stops default coroutine dispatcher.
    """
    Dispatcher.instance().stop()


def spawn(corofunc, *args, **kwargs):
    """ Creates a coroutine created from `corofunc` and given parameters.
    """
    disp = kwargs.pop('disp', Dispatcher.instance())
    coro = corofunc(*args, **kwargs)
    with disp._lock_as_current(coro):
        coro.send(None)
        return coro


def current(*, disp=None):
    """ Returns current coroutine.
    """
    disp = disp or Dispatcher.instance()
    return disp._stack[0] if len(disp._stack) else None


def sleep(seconds, *, disp=None):
    """ Returns awaitable which switch back when given time expired.
    """
    disp = disp or Dispatcher.instance()
    assert isinstance(disp, Dispatcher)
    assert isinstance(seconds, (int, float))
    seconds = seconds if seconds > 0 else 0
    return _Awaitable(disp, disp._event_disp.cancel,
                      disp._event_disp.watch_timer, seconds, True)


def ready(fd, events, *, timeout=None, disp=None):
    """ Returns awaitable which switch back when the I/O device
    with given `fd` will be ready for reading and/or writing or
    timeout expired if set.
    """
    disp = disp or Dispatcher.instance()
    assert isinstance(disp, Dispatcher)
    assert isinstance(fd, int) and fd >= 0
    assert isinstance(events, int)
    assert events & (disp._event_disp.READ | disp._event_disp.WRITE)
    timeout = timeout or 0
    assert isinstance(timeout, (int, float))

    def setup(callback, fd, events, timeout):
        result = True
        if timeout > 0:
            result = disp._event_disp.watch_timer(callback, timeout, True)
        if result:
            result = disp._event_disp.watch_io(callback, fd, events, True)
        if not result:
            disp._event_disp.cance(callback)
        return result

    if timeout < 0:
        raise TimeoutError("I/O timed out")
    return _Awaitable(disp, disp._event_disp.cancel,
                      setup, fd, events, timeout=timeout)


def signal(self, signum, *, disp=None):
    """ Returns awaitable which switch back when the systen signal
    with given `signum` will be received.
    """
    disp = disp or Dispatcher.instance()
    assert isinstance(disp, Dispatcher)
    assert isinstance(signum, int) and signum > 0
    return _Awaitable(disp, disp._event_disp.cancel,
                      disp._event_disp.watch_signal, signum, True)


# utility functions


def timeout_gen(timeout):
    """ Timeouts generator.
    """
    assert ((isinstance(timeout, (int, float)) and timeout >= 0) or
            timeout is None)
    timeout = float(timeout or 0)
    deadline = time() + timeout if timeout else None
    while True:
        left_time = deadline - time()
        yield (None if deadline is None
               else (left_time if left_time > 0 else -1))
