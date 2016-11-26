"""
Implementation of event-driven async/await coroutine switching.
"""
import os
import logging
import threading
from time import time
import multiprocessing
from functools import partial
from collections import deque
from signal import SIGTERM, SIGINT

from squall import abc
from _squall import EventDispatcher
from _squall import READ, WRITE, ERROR, TIMEOUT, SIGNAL, CLEANUP  # noqa

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

    @property
    def running(self):
        """ Returns `True` if this is running.
        """
        return self._event_disp.running

    def spawn(self, corofunc, *args, **kwargs):
        """ Creates a coroutine created from `corofunc` and given parameters.
        """
        coro = corofunc(*args, **kwargs)
        with self._lock_as_current(coro):
            coro.send(None)
        return coro

    def start(self, until_signal=(SIGTERM, SIGINT)):
        """ Starts an event dispatcher and switching of coroutine.
        """
        if isinstance(until_signal, int):
            until_signal = (until_signal, )
        assert isinstance(until_signal, (tuple, list))

        async def terminator(signum):
            await signal(signum)
            self.stop()

        for signum in until_signal:
            self.spawn(terminator, signum)
        self._event_disp.start()

    def stop(self):
        """ Stops it.
        """
        self._event_disp.stop()


class _Awaitable(object):
    """ Create awaitable objects which switches back by call..
    """
    def __init__(self, disp, cancel, setup, *args, **kwargs):
        self._coro = current(disp=disp)
        self._lock_as_current = disp._lock_as_current
        self._cancel = partial(cancel, self)
        self._has_timeout = 'timeout' in kwargs
        self._setup = partial(setup, self, *args, **kwargs)

    def __await__(self):
        if not self._setup():
            raise IOError("Cannot setup event watching")
        try:
            event, payload = yield
            return payload if payload is not None else event
        except GeneratorExit:
            self._cancel()
            raise GeneratorExit

    def __call__(self, event, payload=None):
        self._cancel()
        with self._lock_as_current(self._coro):
            if not event & (ERROR | CLEANUP):
                if self._has_timeout and event & TIMEOUT:
                    self._coro.throw(TimeoutError("I/O timed out"))
                else:
                    self._coro.send((event, payload))
            else:
                if event & ERROR:
                    if payload is not None:
                        if isinstance(payload, Exception):
                            self._coro.throw(payload)
                        elif isinstance(payload, int):
                            exc = IOError(payload, os.strerror(payload))
                            self._coro.throw(exc)
                        else:
                            self._coro.throw(str(payload))
                    else:
                        self._coro.throw(IOError("File descriptor error"))
                else:
                    self._cancel = lambda: None
                    self._coro.close()


class IOStream(object):
    """ Base class for async I/O streams.
    """

    def __init__(self, disp, autobuff):
        assert isinstance(disp, Dispatcher)
        assert isinstance(autobuff, abc.AutoBuffer)
        self._disp = disp
        self._event_disp = disp._event_disp
        self._autobuff = autobuff
        self._finalize = False
        self._closed = False

    @property
    def closed(self):
        """ Returns `True` if this stream is closed.
        """
        return self._closed or self._finalize

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

    @property
    def last_error(self):
        """ Returns last occurred error.
        """
        return self._autobuff.last_error

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
                result = self._event_disp.watch_timer(callback, timeout)
            if result:
                result = self._autobuff.watch_read_bytes(callback, number)
            if not result:
                cancel(callback)
            return result

        if self._finalize or self._closed:
            raise ConnectionError("Connection has closed")
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
        max_number = max_number or 0
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
                result = self._event_disp.watch_timer(callback, timeout)
            if result:
                result = self._autobuff.watch_read_until(callback, delimiter,
                                                         max_number)
            if not result:
                cancel(callback)
            return result

        if self._finalize or self._closed:
            raise ConnectionError("Connection has closed")
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
                result = self._event_disp.watch_timer(callback, timeout)
            if result:
                result = self._autobuff.watch_flush(callback)
            if not result:
                cancel(callback)
            return result

        if self._closed and not self._finalize:
            raise ConnectionError("Connection has closed")
        if timeout < 0:
            raise TimeoutError("I/O timed out")
        return _Awaitable(self._disp, cancel,
                          setup, timeout=timeout)

    def write(self, data):
        """ Puts `data` bytes to outcoming buffer.
        """
        if self._finalize or self._closed:
            raise ConnectionError("Connection has closed")
        assert isinstance(data, bytes)
        return self._autobuff.write(data)

    async def close(self, timeout=None):
        """ Closes a stream asynchronously.
        """
        if self._closed:
            raise ConnectionError("Connection has closed")
        if not self._finalize:
            self._finalize = True
            await self.flush(timeout=timeout)
            self.abort()

    def abort(self):
        """ Closes a stream and releases resources immediately.
        """
        self._closed = True
        self._autobuff.release()


def start(*, disp=None, worker=1,
          until_signal=(SIGTERM, SIGINT)):
    """ Starts default coroutine dispatcher.
    """
    disp = disp or Dispatcher.instance()
    if isinstance(until_signal, int):
        until_signal = (until_signal, )
    assert isinstance(until_signal, (tuple, list))
    if worker < 1:
        worker = multiprocessing.cpu_count()
    if worker > 1:
        main_disp = Dispatcher()

        async def process_holder():
            process = multiprocessing.Process(target=disp.start, daemon=True)
            process.start()
            try:
                await ready(process.sentinel, READ, disp=main_disp)
            except IOError:
                pass
            # finally:
            #     if main_disp.running:
            #         logging.error("Child process: {} has terminated."
            #                       "".format(process.pid))

        for _ in range(worker):
            main_disp.spawn(process_holder)

        async def terminator(sigint):
            await signal(sigint, disp=main_disp)
            main_disp.stop()

        main_disp.spawn(terminator, SIGTERM)
        main_disp.spawn(terminator, SIGINT)
        main_disp.start(until_signal=until_signal)

    else:
        disp.start()


def stop(*, disp=None):
    """ Stops default coroutine dispatcher.
    """
    disp = disp or Dispatcher.instance()
    disp.stop()


def spawn(corofunc, *args, **kwargs):
    """ Creates a coroutine created from `corofunc` and given parameters.
    """
    disp = kwargs.get('disp', Dispatcher.instance())
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
                      disp._event_disp.watch_timer, seconds)


def ready(fd, events, *, timeout=None, disp=None):
    """ Returns awaitable which switch back when the I/O device
    with given `fd` will be ready for reading and/or writing or
    timeout expired if set.
    """
    disp = disp or Dispatcher.instance()
    assert isinstance(disp, Dispatcher)
    assert isinstance(fd, int) and fd >= 0
    assert isinstance(events, int)
    assert events & (READ | WRITE)
    timeout = timeout or 0
    assert isinstance(timeout, (int, float))

    def setup(callback, fd, events, timeout):
        result = True
        if timeout > 0:
            result = disp._event_disp.watch_timer(callback, timeout)
        if result:
            result = disp._event_disp.watch_io(callback, fd, events)
        if not result:
            disp._event_disp.cance(callback)
        return result

    if timeout < 0:
        raise TimeoutError("I/O timed out")
    return _Awaitable(disp, disp._event_disp.cancel,
                      setup, fd, events, timeout=timeout)


def signal(signum, *, disp=None):
    """ Returns awaitable which switch back when the systen signal
    with given `signum` will be received.
    """
    disp = disp or Dispatcher.instance()
    assert isinstance(disp, Dispatcher)
    assert isinstance(signum, int) and signum > 0
    return _Awaitable(disp, disp._event_disp.cancel,
                      disp._event_disp.watch_signal, signum)


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
