"""
Implementation of event-driven async/await coroutine switching.
"""
import os
import logging
import threading
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
    _tls.instance = None
    _tls.stack = deque()

    def __init__(self):
        self._event_disp = EventDispatcher()

    class _AsCurrent(object):

        def __init__(self, disp, coro):
            self._disp = disp
            self._coro = coro

        def __enter__(self):
            type(self._disp)._tls.stack.appendleft((self._coro, self._disp))
            return self

        def __exit__(self, exc_type, exc_value, exc_traceback):
            coro, disp = type(self._disp)._tls.stack.popleft()
            assert disp == self._disp
            assert coro == self._coro
            if exc_type is not None:
                if exc_type not in (StopIteration, GeneratorExit):
                    logger.error("Coroutine %s closed"
                                 " due to uncaught exception", coro,
                                 exc_info=(exc_type, exc_value, exc_traceback))
                return True

    def _as_current(self, coro):
        return self._AsCurrent(self, coro)

    @classmethod
    def instance(cls):
        """ Returns default (thread local) instance.
        """
        if cls._tls.instance is None:
            cls._tls.instance = cls()
        return cls._tls.instance

    @classmethod
    def current(cls):
        """ Returns a running coroutine and its dispatcher.
        """
        return cls._tls.stack[0] if len(cls._tls.stack) else (None, None)

    @property
    def running(self):
        """ Returns `True` if this is running.
        """
        return self._event_disp.running

    def spawn(self, corofunc, *args, **kwargs):
        """ Creates a coroutine created from `corofunc` and given parameters.
        """
        coro = corofunc(*args, **kwargs)
        with self._as_current(coro):
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
    def __init__(self, cancel, setup, *args, **kwargs):
        self._coro, self._disp = Dispatcher.current()
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
        with self._disp._as_current(self._coro):
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


def start(*, disp=None, workers=1,
          until_signal=(SIGTERM, SIGINT)):
    """ Starts default coroutine dispatcher.
    """
    disp = disp or Dispatcher.instance()
    if isinstance(until_signal, int):
        until_signal = (until_signal, )
    assert isinstance(until_signal, (tuple, list))
    if workers < 1:
        workers = multiprocessing.cpu_count()
    if workers > 1:
        processes = dict()
        main_disp = Dispatcher()

        for _ in range(workers):
            process = multiprocessing.Process(target=disp.start, daemon=True)
            process.start()
            processes[process.sentinel] = process

        async def terminator(sigint):
            await signal(sigint)
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
    return disp.spawn(corofunc, *args, **kwargs)


def sleep(seconds):
    """ Returns awaitable which switch back when given time expired.
    """
    _, disp = Dispatcher.current()
    assert disp is not None
    event_disp = disp._event_disp
    assert isinstance(seconds, (int, float))
    seconds = seconds if seconds > 0 else 0
    return _Awaitable(event_disp.cancel,
                      event_disp.watch_timer, seconds)


def ready(fd, events, *, timeout=None, disp=None):
    """ Returns awaitable which switch back when the I/O device
    with given `fd` will be ready for reading and/or writing or
    timeout expired if set.
    """
    _, disp = Dispatcher.current()
    assert disp is not None
    event_disp = disp._event_disp
    assert isinstance(fd, int) and fd >= 0
    assert isinstance(events, int)
    assert events & (READ | WRITE)
    timeout = timeout or 0
    assert isinstance(timeout, (int, float))

    def setup(callback, fd, events, timeout):
        result = True
        if timeout > 0:
            result = event_disp.watch_timer(callback, timeout)
        if result:
            result = event_disp.watch_io(callback, fd, events)
        if not result:
            event_disp.cance(callback)
        return result

    if timeout < 0:
        raise TimeoutError("I/O timed out")
    return _Awaitable(event_disp.cancel,
                      setup, fd, events, timeout=timeout)


def signal(signum, *, disp=None):
    """ Returns awaitable which switch back when the systen signal
    with given `signum` will be received.
    """
    _, disp = Dispatcher.current()
    assert disp is not None
    event_disp = disp._event_disp
    assert isinstance(signum, int) and signum > 0
    return _Awaitable(event_disp.cancel,
                      event_disp.watch_signal, signum)
