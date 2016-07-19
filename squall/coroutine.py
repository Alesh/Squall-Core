"""
Implementation of event-driven async/await coroutine switching.
"""
import errno
import logging

from collections import deque
from signal import SIGINT, SIGTERM

try:
    from squall import _squall as dispatcher
    from squall._squall import READ, WRITE, ERROR, TIMEOUT
except ImportError:
    from squall._failback import dispatcher
    from squall._failback.dispatcher import READ, WRITE, ERROR, TIMEOUT  # noqa

logger = logging.getLogger(__name__)


class _SwitchBack(object):

    """ Makes future-like object that will ensure the execution return back
    to the coroutine when the awaited event occurs. One coroutine - one object
    this class for the entire coroutine lifetime.

    :param callable setup: Callable, which sets the event dispatcher
        to notify if awaited events occurred. ``*args``, ``**kwargs``
        it its parameters.
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
        self._setup(self, *self._args, **self._kwargs)
        try:
            cls._current.popleft()
            revents, payload = yield
        except GeneratorExit:
            # exception while coroutine waiting
            self.__release()
            return

        if revents == dispatcher.TIMEOUT and 'timeout' in self._kwargs:
            raise TimeoutError(errno.ETIMEDOUT, "Connection timed out")
        elif revents == dispatcher.CLEANUP:
            raise GeneratorExit
        elif revents == dispatcher.ERROR:
            if payload is not None:
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
    dispatcher.setup_wait(lambda *args: dispatcher.stop(), 0)


def current():
    """ Returns coroutine which running at this moment.
    """
    return _SwitchBack._current[0] if len(_SwitchBack._current) else None


def spawn(corofunc, *args, **kwargs):
    """ Creates, starts and returns coroutine based on given ``corofunc``.
    """
    coro = corofunc(*args, **kwargs)
    _SwitchBack._current.appendleft(coro)
    coro.send(None)
    return coro


def sleep(timeout=None):
    """ Freezes current coroutine until ``timeout`` elapsed.
    """
    assert ((isinstance(timeout, (int, float)) and
            timeout >= 0) or timeout is None)
    return _SwitchBack(dispatcher.setup_wait, float(timeout or 0))


def ready(fd, mode, *, timeout=None):
    """ Freezes the current coroutine until I/O device is ready.
    ``fd`` and ``mode`` defines device and expected events:
    ``READ`` and/or ``WRITE``.
    """
    assert isinstance(fd, int) and fd >= 0
    assert mode in (READ, WRITE, READ | WRITE)
    assert ((isinstance(timeout, (int, float)) and
            timeout >= 0) or timeout is None)

    # setup I/O ready and timeout both
    def setup_ready(target, fd, mode, timeout):
        dispatcher.setup_wait_io(target, fd, mode)
        if timeout > 0:
            dispatcher.setup_wait(target, timeout)
    return _SwitchBack(setup_ready, fd, mode, timeout=float(timeout or 0))


def signal(signum):
    """ Freezes the current coroutine until system signal with given ``signum``
    """
    assert isinstance(signum, int) and signum > 0 and signum <= 64
    return _SwitchBack(dispatcher.setup_wait_signal, signum)


def run(on_stop=None):
    """ Runs the event dispatching until SIGINT or SIGTERM.
    """
    async def terminator(signum):
        await signal(signum)
        if on_stop is None:
            stop()
        else:
            on_stop()

    for signum in (SIGTERM, SIGINT):
        spawn(terminator, signum)
    start()
