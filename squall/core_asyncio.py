""" Module of callback classes based on asyncio
"""
import asyncio
import logging

from squall.core_.abc import EventLoop as AbcEventLoop


class EventLoop(AbcEventLoop):
    """ asyncio based implementation of `squall.core_.abc.EventLoop`
    """

    READ = 1
    WRITE = 2

    def __init__(self):
        self._fds = dict()
        self._pendings = 0
        self._signals = dict()
        self._loop = asyncio.get_event_loop()
        super().__init__()

    def _inc_pending(self):
        self._pendings += 1

    def _dec_pending(self):
        def check_fishish():
            if self._pendings == 0:
                self.stop()

        self._pendings -= 1
        if self._pendings == 0:
            self._loop.call_soon(check_fishish)

    def start(self):
        """ See for detail `AbcEventLoop.start` """
        logging.info("Using asyncio based callback classes")
        self._loop.run_forever()

    def stop(self):
        """ See for detail `AbcEventLoop.stop` """
        self._loop.stop()

    def setup_timeout(self, callback, seconds, result=True):
        """ See for detail `AbcEventLoop.setup_timeout` """
        deadline = self._loop.time() + seconds
        handle = self._loop.call_at(deadline, callback, result)
        self._inc_pending()
        return handle

    def cancel_timeout(self, handle):
        """ See for detail `AbcEventLoop.cancel_timeout` """
        handle.cancel()
        self._dec_pending()

    def setup_ready(self, callback, fd, events):
        """ See for detail `AbcEventLoop.setup_ready` """
        assert events & (self.READ | self.WRITE) == events
        if events & self.READ:
            self._loop.add_reader(fd, callback, self.READ)
        if events & self.WRITE:
            self._loop.add_writer(fd, callback, self.WRITE)
        self._fds[fd] = [callback, events]
        self._inc_pending()
        return fd

    def update_ready(self, handle, events):
        """ See for detail `AbcEventLoop.setup_ready` """
        fd = handle
        callback, _events = self._fds[fd]
        if _events != events:
            if (events & self.READ) and not (_events & self.READ):
                self._loop.add_reader(fd, callback, self.READ)
            elif (_events & self.READ) and not (events & self.READ):
                self._loop.remove_reader(fd)
            if (events & self.WRITE) and not (_events & self.WRITE):
                self._loop.add_writer(fd, callback, self.WRITE)
            elif (_events & self.WRITE) and not (events & self.WRITE):
                self._loop.remove_writer(fd)
            self._fds[fd][1] = events

    def cancel_ready(self, handle):
        """ See for detail `AbcEventLoop.cancel_ready` """
        fd = handle
        _, events = self._fds.pop(fd)
        assert events & (self.READ | self.WRITE) == events
        if events & self.READ:
            self._loop.remove_reader(fd)
        if events & self.WRITE:
            self._loop.remove_writer(fd)
        self._dec_pending()

    def _handle_signal(self, signum):
        for callback in tuple(self._signals[signum]):
            self._loop.call_soon(callback, signum)

    def setup_signal(self, callback, signum):
        """ See for detail `AbcEventLoop.setup_signal` """
        if signum not in self._signals:
            self._loop.add_signal_handler(signum, self._handle_signal, signum)
            self._signals[signum] = list()
        self._signals[signum].append(callback)
        self._inc_pending()
        return signum, callback

    def cancel_signal(self, handler):
        """ See for detail `AbcEventLoop.cancel_signal` """
        signum, callback = handler
        if signum in self._signals:
            self._signals[signum].remove(callback)
            self._dec_pending()
