"""
Low-level event dispatcher and I/O autobuffer designed
for use with a callback functions.
"""
import signal
from time import time
from tornado.ioloop import IOLoop
from squall import abc


class EventDispatcher(abc.EventDispatcher):
    """ Sample event dispatcher.
    """
    TIMEOUT = 0x100
    READ = IOLoop.READ
    WRITE = IOLoop.WRITE
    ERROR = IOLoop.ERROR
    CLEANUP = 0x40000
    SIGNAL = 0x400

    def __init__(self):
        self._cleanup = False
        self._signals = dict()
        self._cancels = dict()
        self._loop = IOLoop(make_current=False)

    def _handle_signal(self, signum, frame):
        for callback in tuple(self._signals[signum].values()):
            self._loop.add_callback_from_signal(callback, self.SIGNAL)

    def _watch_signal(self, ctx, callback, signum):
        if signum not in self._signals:
            signal.signal(signum, self._handle_signal)
            self._signals[signum] = dict()
        self._signals[signum][ctx] = callback

    def _cancel_signal(self, ctx, signum):
        if signum in self._signals:
            self._signals[signum].pop(ctx, None)

    def start(self):
        """ Starts event dispatcher.
        """
        """ See: `abc.EventDispatcher.start` """
        self.watch_signal(lambda *args: self.stop(), signal.SIGINT, True)
        self._loop.start()

    def stop(self):
        """ Stops event dispatcher.
        """
        def deferred_stop(revents):
            self._cleanup = True
            for callback, cancels in tuple(self._cancels.items()):
                self.cancel(callback)
                if any(cancels):
                    callback(self.CLEANUP)
            self._loop.stop()
            self._loop.close(True)
            self._loop = IOLoop(make_current=False)
            self._cleanup = False
        # deferred stop!
        self.watch_timer(deferred_stop, 0, True)

    def watch_timer(self, callback, seconds, once=False):
        """ Sets an event dispatcher to call `callback` with code `TIMEOUT`
        after a specified time in seconds.
        """
        def timeout_callback(revents):
            self._cancels[callback][0] = None
            renew = True
            if revents is not None:
                if once:
                    self.cancel(callback)
                renew = callback(revents) and not once
            if renew:
                if (not self._cleanup and callback in self._cancels and
                        self._cancels[callback][0] is None):
                    handle = self._loop.add_timeout(
                        time() + seconds, timeout_callback, self.TIMEOUT)
                    self._cancels[callback][0] = \
                        lambda: self._loop.remove_timeout(handle)
            else:
                if (callback in self._cancels and
                        not any(self._cancels[callback])):
                    self._cancels.pop(callback)
        if seconds >= 0 and not self._cleanup:
            if callback not in self._cancels:
                self._cancels[callback] = [None, None, None]
            else:
                if self._cancels[callback][0] is not None:
                    self._cancels[callback][0]()
            timeout_callback(None)
            return True
        return False

    def watch_io(self, callback, fd, events, once=False):
        """ Sets an event dispatcher to call `callback` with code `READ`
        and/or `WRITE` when I/O device  with given `fd` will be ready
        for corresponding I/O operations.
        """
        def io_callback(fd, revents):
            io_cancel = self._cancels[callback][1]
            self._cancels[callback][1] = None
            renew = True
            if revents is not None:
                if once:
                    io_cancel()
                    io_cancel = None
                    self.cancel(callback)
                renew = callback(revents) and not once
                if io_cancel is not None and callback not in self._cancels:
                    io_cancel()
                if renew:
                    if (not self._cleanup and callback in self._cancels and
                            self._cancels[callback][1] is None):
                        self._cancels[callback][1] = io_cancel
                else:
                    if io_cancel is not None:
                        io_cancel()
                    if (callback in self._cancels and
                            not any(self._cancels[callback])):
                        self._cancels.pop(callback)
            else:
                self._loop.add_handler(fd, io_callback, events)
                self._cancels[callback][1] = \
                    lambda: self._loop.remove_handler(fd)

        if fd >= 0 and events > 0 and not self._cleanup:
            if callback not in self._cancels:
                self._cancels[callback] = [None, None, None]
            else:
                if self._cancels[callback][1] is not None:
                    self._cancels[callback][1]()
            io_callback(fd, None)
            return True
        return False

    def watch_signal(self, callback, signum, once):
        """ Sets an event dispatcher to call `callback` with code `SIGNAL`
        when a systems signal with given `signum` will be received.
        """
        def signal_callback(revents):
            self._cancel_signal(callback, signum)
            self._cancels[callback][2] = None
            renew = True
            if revents is not None:
                if once:
                    self.cancel(callback)
                renew = callback(revents) and not once
            if renew:
                if (not self._cleanup and callback in self._cancels and
                        self._cancels[callback][2] is None):
                    self._watch_signal(callback, signal_callback, signum)
                    self._cancels[callback][2] = \
                        lambda: self._cancel_signal(callback, signum)
            else:
                if (callback in self._cancels and
                        not any(self._cancels[callback])):
                    self._cancels.pop(callback)

        if signum > 0 and not self._cleanup:
            if callback not in self._cancels:
                self._cancels[callback] = [None, None, None]
            else:
                if self._cancels[callback][2] is not None:
                    self._cancels[callback][2]()
            signal_callback(None)
            return True
        return False

    def cancel(self, callback):
        """ Cancels all watchings for a given `callback`.
        """
        if callback in self._cancels:
            for cancel in self._cancels.pop(callback):
                if cancel is not None:
                    cancel()
