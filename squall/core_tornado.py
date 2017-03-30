""" Module of callback classes based on tornado
"""
import logging
import signal
from time import time

from squall.core_.abc import EventLoop as AbcEventLoop
from tornado.ioloop import IOLoop


class EventLoop(AbcEventLoop):
    """ tornado based implementation of `squall.core_.abc.EventLoop`
    """

    READ = IOLoop.READ
    WRITE = IOLoop.WRITE

    def __init__(self):
        self._signals = dict()
        self._loop = IOLoop(make_current=False)
        super().__init__()

    def start(self):
        """ See for detail `AbcEventLoop.start` """
        logging.info("Using tornado based callback classes")
        self._loop.start()

    def stop(self):
        """ See for detail `AbcEventLoop.stop` """
        self._loop.stop()

    def setup_timeout(self, callback, seconds, result=True):
        """ See for detail `AbcEventLoop.setup_timeout` """
        deadline = time() + seconds
        handle = self._loop.add_timeout(deadline, callback, result)
        return handle

    def cancel_timeout(self, handle):
        """ See for detail `AbcEventLoop.setup_timeout` """
        self._loop.remove_timeout(handle)

    def setup_ready(self, callback, fd, events):
        """ See for detail `AbcEventLoop.setup_ready` """

        def handler(_, revents):
            if revents & IOLoop.ERROR:
                callback(IOError("Internal eventloop error"))
            else:
                callback(revents)

        self._loop.add_handler(fd, handler, events)
        return fd

    def update_ready(self, handle, events: int):
        """ See for detail `AbcEventLoop.update_ready` """
        fd = handle
        self._loop.update_handler(fd, events)

    def cancel_ready(self, handle):
        """ See for detail `AbcEventLoop.cancel_ready` """
        fd = handle
        self._loop.remove_handler(fd)

    def _handle_signal(self, signum, _):
        for callback in tuple(self._signals[signum]):
            self._loop.add_callback_from_signal(callback, signum)

    def setup_signal(self, callback, signum):
        """ See for detail `AbcEventLoop.setup_signal` """
        if signum not in self._signals:
            signal.signal(signum, self._handle_signal)
            self._signals[signum] = list()
        if callback not in self._signals[signum]:
            self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handler):
        """ See for detail `AbcEventLoop.cancel_signal` """
        signum, callback = handler
        if signum in self._signals:
            self._signals[signum].remove(callback)
