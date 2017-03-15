""" Module of callback classes based on tornado
"""
import signal
from time import time

from squall.core.native.cb import abc
from squall.core.utils import logger
from tornado.ioloop import IOLoop


class EventLoop(abc.EventLoop):
    """ tornado based implementation of `abc.EventLoop`
    """

    READ = IOLoop.READ
    WRITE = IOLoop.WRITE

    def __init__(self):
        self._signals = dict()
        self._loop = IOLoop(make_current=False)
        super().__init__()

    def start(self):
        """ See: `abc.EventLoop.start` """
        logger.info("Using tornado based callback classes")
        self._loop.start()

    def stop(self):
        """ See: `abc.EventLoop.stop` """
        self._loop.stop()

    def setup_timeout(self, callback, seconds, result=True):
        """ See: `abc.EventLoop.setup_timeout` """
        deadline = time() + seconds
        return self._loop.add_timeout(deadline, callback, result)

    def cancel_timeout(self, handle):
        """ See: `abc.EventLoop.setup_timeout` """
        self._loop.remove_timeout(handle)

    def setup_ready(self, callback, fd, events):
        """ See: `abc.EventLoop.setup_ready` """

        def handler(_, revents):
            if events & IOLoop.ERROR:
                callback(IOError("Internal eventloop error"))
            else:
                callback(revents)

        self._loop.add_handler(fd, handler, events)
        return fd

    def cancel_ready(self, handle):
        """ See: `abc.EventLoop.cancel_ready` """
        self._loop.remove_handler(handle)

    def _handle_signal(self, signum, _):
        for callback in tuple(self._signals[signum]):
            self._loop.add_callback_from_signal(callback, signum)

    def setup_signal(self, callback, signum):
        """ See: `abc.EventLoop.setup_signal` """
        if signum not in self._signals:
            signal.signal(signum, self._handle_signal)
            self._signals[signum] = list()
        if callback not in self._signals[signum]:
            self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handler):
        """ See: `abc.EventLoop.cancel_signal` """
        signum, callback = handler
        if signum in self._signals:
            self._signals[signum].remove(callback)
