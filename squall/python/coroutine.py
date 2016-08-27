"""
Implementation of event-driven async/await coroutine switching.
"""
import os
import errno
import logging
from collections import deque
from signal import SIGINT, SIGTERM
import _squall

READ = _squall.Dispatcher.READ
WRITE = _squall.Dispatcher.WRITE
ERROR = _squall.Dispatcher.ERROR
TIMEOUT = _squall.Dispatcher.TIMER
SIGNAL = _squall.Dispatcher.SIGNAL
dispatcher = _squall.Dispatcher.current()

logger = logging.getLogger(__name__)


class Error(Exception):
    """ Base error. """


class CannotSetupWatcher(Error):
    """ Cannot setup watcher error. """


class _SwitchBack(object):

    """ Makes the future-like object that will ensure execution
    return back to a coroutine when awaited event occurs.
    """

    _all = dict()
    _current = deque()

    def __new__(cls, *args, **kwargs):
        coro = cls._current[0]
        if coro not in cls._all:
            inst = object.__new__(cls)
            inst._coro = coro
            cls._all[coro] = inst
        return cls._all[coro]

    def __init__(self, setup, *args, **kwargs):
        self._setup = setup
        self._args = args
        self._kwargs = kwargs

    def __call__(self, event, payload=None):
        """ Event handler, called from an event dispatcher.
        """
        cls = self.__class__
        try:
            cls._current.appendleft(self._coro)
            self._coro.send((event, payload))
        except (Exception, GeneratorExit) as exc:
            # exception while coroutine running
            if not isinstance(exc, (StopIteration, GeneratorExit)):
                logging.exception("Coroutine '%s' terminated by"
                                  " uncaught exception", self._coro)
            self.__release()

    def __await__(self):
        """ Makes awaitable, called from a coroutine.
        """
        cls = self.__class__
        try:
            result = self._setup(self, *self._args, **self._kwargs)
            if result is not None:
                return result
        except RuntimeError as exc:
            if dispatcher.active:
                raise exc
            else:
                raise GeneratorExit
        try:
            cls._current.popleft()
            revents, payload = yield
        except GeneratorExit:
            # exception while coroutine waiting
            self.__release()
            return
        if revents == TIMEOUT and 'timeout' in self._kwargs:
            raise TimeoutError(errno.ETIMEDOUT, "Connection timed out")
        elif revents == dispatcher.CLEANUP:
            raise GeneratorExit
        elif revents == dispatcher.ERROR:
            if payload is not None:
                if isinstance(payload, int):
                    if payload in errno.errorcode:
                        raise IOError(payload, os.strerror(payload))
                else:
                    raise payload
            else:
                raise IOError(errno.EIO, "Undefined event loop error")
        return payload if payload is not None else revents

    def __release(self):
        cls = self.__class__
        cls._all.pop(self._coro)
        try:
            cls._current.remove(self._coro)
        except ValueError:
            pass
        dispatcher.release_watching(self)


def start():
    """ Starts event dispatching.
    """
    dispatcher.start()


def stop():
    """ Stops event dispatching.
    """
    dispatcher.stop()


def current():
    """ Returns coroutine which running at this moment.
    """
    return _SwitchBack._current[0] if len(_SwitchBack._current) else None


def spawn(corofunc, *args, **kwargs):
    """ Creates, starts and returns the coroutine based on a ``corofunc``.
    """
    coro = corofunc(*args, **kwargs)
    _SwitchBack._current.appendleft(coro)
    coro.send(None)
    return coro


def sleep(timeout=None):
    """ Freezes a current coroutine until ``timeout`` elapsed.
    """
    assert ((isinstance(timeout, (int, float)) and
            timeout >= 0) or timeout is None)
    return _SwitchBack(dispatcher.watch_timer, float(timeout or 0))


def wait_io(fd, mode, *, timeout=None):
    """ Freezes a current coroutine until I/O device is ready.
    """
    assert isinstance(fd, int) and fd >= 0
    assert mode in (READ, WRITE, READ | WRITE)
    assert ((isinstance(timeout, (int, float)) and
            timeout >= 0) or timeout is None)

    # setup I/O ready and timeout both
    def watch_io(target, fd, mode, timeout):
        dispatcher.watch_io(target, fd, mode)
        if timeout > 0:
            dispatcher.watch_timer(target, timeout)
    return _SwitchBack(watch_io, fd, mode, timeout=float(timeout or 0))


def wait_signal(signum):
    """ Freezes a current coroutine until received signal with ``signum``..
    """
    assert isinstance(signum, int) and signum > 0 and signum <= 64
    return _SwitchBack(dispatcher.watch_signal, signum)


def run(on_stop=None):
    """ Runs the event dispatching until `SIGINT` or `SIGTERM`.
    """
    async def terminator(signum):
        await wait_signal(signum)
        if on_stop is None:
            stop()
        else:
            on_stop()

    for signum in (SIGTERM, SIGINT):
        spawn(terminator, signum)
    start()
