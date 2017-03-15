""" Module of callback classes based on asyncio
"""
import asyncio

from squall.core.native.cb import abc
from squall.core.utils import logger


class EventLoop(abc.EventLoop):
    """ asyncio based implementation of `squall.core.native.cb.abc.EventLoop`
    """

    READ = 1
    WRITE = 2

    def __init__(self):
        self._signals = dict()
        self._loop = asyncio.get_event_loop()
        super().__init__()

    def start(self):
        """ See: `abc.EventLoop.start` """
        logger.info("Using asyncio based callback classes")
        self._loop.run_forever()

    def stop(self):
        """ See: `abc.EventLoop.stop` """
        self._loop.stop()

    def setup_timeout(self, callback, seconds, result=True):
        """ See: `abc.EventLoop.setup_timeout` """
        deadline = self._loop.time() + seconds
        return self._loop.call_at(deadline, callback, result)

    def cancel_timeout(self, handle):
        """ See: `abc.EventLoop.cancel_timeout` """
        handle.cancel()

    def setup_ready(self, callback, fd, events):
        """ See: `abc.EventLoop.setup_ready` """
        if events & self.READ:
            self._loop.add_reader(fd, callback, self.READ)
        if events & self.WRITE:
            self._loop.add_writer(fd, callback, self.WRITE)
        return fd, events

    def cancel_ready(self, handle):
        """ See: `abc.EventLoop.cancel_ready` """
        fd, events = handle
        if events & self.READ:
            self._loop.remove_reader(fd)
        if events & self.WRITE:
            self._loop.remove_writer(fd)

    def _handle_signal(self, signum):
        for callback in tuple(self._signals[signum]):
            self._loop.call_soon(callback, signum)

    def setup_signal(self, callback, signum):
        """ See: `abc.EventLoop.setup_signal` """
        if signum not in self._signals:
            self._loop.add_signal_handler(signum, self._handle_signal, signum)
            self._signals[signum] = list()
        self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handler):
        """ See: `abc.EventLoop.cancel_signal` """
        signum, callback = handler
        if signum in self._signals:
            self._signals[signum].remove(callback)
