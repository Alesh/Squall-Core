"""
Event-driven coroutine switching
================================
"""
import errno
import logging
import signal as sys_signal
from time import time as now

from tornado import gen
from tornado.ioloop import IOLoop
from tornado.concurrent import Future
from tornado.log import enable_pretty_logging

READ = IOLoop.READ
WRITE = IOLoop.WRITE
ERROR = IOLoop.ERROR
TIMEOUT = 0x100
SIGNAL = 0x400

enable_pretty_logging()
logger = logging.getLogger(__name__)


def start():
    """ Starts event dispatching.
    """
    loop = IOLoop.current()
    logger.warning("Using failback event dispatcher based on Tornado")
    try:
        loop.start()
    except KeyboardInterrupt:
        loop.stop()


def spawn(corofunc, *args, **kwargs):
    """ Creates, starts and returns coroutine based on given ``corofunc``.
    """
    IOLoop.current().spawn_callback(corofunc, *args, **kwargs)


def stop():
    """ Stops event dispatching.
    """
    IOLoop.current().stop()


async def sleep(seconds=None):
    """ Freezes current coroutine until ``seconds`` elapsed.
    """
    assert ((isinstance(seconds, (int, float)) and
            seconds >= 0) or seconds is None)
    await gen.sleep(seconds or 0)
    return TIMEOUT


async def ready(fd, mode, *, timeout=None):
    """ Freezes the current coroutine until I/O device is ready.
    ``fd`` and ``mode`` defines device and
    expected events: ``READ`` and/or ``WRITE``.
    """
    assert isinstance(fd, int) and fd >= 0
    assert mode in (READ, WRITE, READ | WRITE)
    assert ((isinstance(timeout, (int, float)) and
            timeout >= 0) or timeout is None)
    loop = IOLoop.current()
    future = Future()

    def callback(fd, events):
        loop.remove_handler(fd)
        future.set_result(events)

    def set_wait(fd, mode, timeout):
        loop.add_handler(fd, callback, mode)
        if timeout:
            deadline = now() + timeout
            return gen.with_timeout(deadline, future, loop)
        else:
            return future

    try:
        return await set_wait(fd, mode, timeout)
    except gen.TimeoutError:
        loop.remove_handler(fd)
        raise TimeoutError(errno.ETIMEDOUT, "I/O timed out")


_signal_pendings = dict()


def _signal_handler(signum, frame):
    if signum in _signal_pendings:
        for callback, loop in _signal_pendings[signum].items():
            loop.add_callback_from_signal(callback)


def _stop_signal(loop, callback, signum):
    if signum in _signal_pendings:
        if callback in _signal_pendings[signum]:
            _signal_pendings[signum].pop(callback, None)


def _start_signal(loop, callback, signum):
    if signum not in _signal_pendings:
        _signal_pendings[signum] = dict()
        sys_signal.signal(signum, _signal_handler)
    _signal_pendings[signum][callback] = loop


async def signal(signum):
    """ Freezes the current coroutine until system signal with given ``signum``
    """
    assert isinstance(signum, int) and signum > 0 and signum <= 64
    loop = IOLoop.current()
    future = Future()

    def callback():
        _stop_signal(loop, callback, signum)
        future.set_result(SIGNAL)
    _start_signal(loop, callback, signum)
    return await future


def run():
    """ Runs the event dispatching until SIGINT or SIGTERM.
    """
    async def terminator(signum):
        await signal(signum)
        stop()

    for signum in (sys_signal.SIGTERM, sys_signal.SIGINT):
        spawn(terminator, signum)
    start()
