""" Failback event dispatcher based on tornado.
"""
import time
import signal
import logging

import tornado.log
import tornado.ioloop

tornado.log.enable_pretty_logging()
logger = logging.getLogger('squall')
logger.warning("Using failback event dispatcher based on Tornado")


class Dispatcher(object):

    """ Event dispatcher based on tornado.
    """

    READ = tornado.ioloop.IOLoop.READ
    WRITE = tornado.ioloop.IOLoop.WRITE
    ERROR = tornado.ioloop.IOLoop.ERROR
    CLEANUP = 0x40000
    TIMER = 0x100
    SIGNAL = 0x400

    def __init__(self):
        self._exc = None
        self._actives = 0
        self.__loop = None
        self._running = False
        self._cleanup = False
        self._targets = dict()
        self._timer_pendings = dict()
        self._signal_pendings = dict()

    @property
    def _loop(self):
        if self.__loop is None:
            self.__loop = tornado.ioloop.IOLoop()
        return self.__loop

    @classmethod
    def current(cls):
        """ Current (thread local) instance """
        if not hasattr(cls, "_current"):
            cls._current = cls()
        return cls._current

    def start(self):
        """ Starts event dispatching. """
        self._running = True
        try:
            self._loop.start()
            if self._exc is not None:
                raise self._exc
        except KeyboardInterrupt:
            self._cleanup = True
            self._loop.stop()
        finally:
            self._release()
            # self.__loop.clear_instance()
            self.__loop.close(True)
            self._running = False
            self._cleanup = False
            self.__loop = None

    def stop(self, exc=None):
        """ Stops event dispatching. """
        if self._running:
            self._exc = exc
            self._loop.add_callback(lambda: self._loop.stop())
        elif not self._cleanup:
            self._release()
            if exc is not None:
                raise exc

    def watch_io(self, target, fd, mask):
        """ Sets up I/O event watching. """
        # print("... watch_io{}".format((self, target, fd, mask)))
        def callback(fd, events):
            self._event_handler(target, events, fd)

        return self._reset_watching(
            target, 0, fd,
            lambda: self._loop.add_handler(fd, callback, mask),
            lambda: self._loop.remove_handler(fd))

    def watch_timer(self, target, secs):
        """ Sets up timeout watching. """
        # print("... watch_timer{}".format((self, target, secs)))
        def callback():
            self._event_handler(target, self.TIMER)

        return self._reset_watching(
            target, 1, 0,
            lambda: self._start_timeout(self._loop, secs, callback),
            lambda: self._stop_timeout(self._loop, callback))

    def watch_signal(self, target, signum):
        """ Sets up system sygnal watching. """
        def callback():
            self._event_handler(target, self.SIGNAL, signum)

        return self._reset_watching(
            target, 2, signum,
            lambda: self._start_signal(self._loop, signum, callback),
            lambda: self._stop_signal(self._loop, signum, callback))

    def disable_watching(self, target):
        """ Disables all associated watching for given event target. """
        # print("... disable_watching{}".format((self, target)))
        found = self._targets.get(target)
        if found is not None:
            for index in range(0, 3):
                for watcher in found[index].values():
                    active, enable, disable = watcher
                    if active:
                        disable()
                        watcher[0] = False
                        self._actives -= 1
            return True
        return False

    def enable_watching(self, target):
        """ Enables all associated watching for given event target. """
        # print("... enable_watching{}".format((self, target)))
        found = self._targets.get(target)
        if found is not None:
            for index in range(0, 3):
                for watcher in found[index].values():
                    active, enable, disable = watcher
                    if not active:
                        enable()
                        watcher[0] = True
                        self._actives += 1
            return True
        return False

    def release_watching(self, target):
        """ Releases given event target and all associated watching. """
        # print("... release_watching{}".format((self, target)))
        if self.disable_watching(target):
            self._targets.pop(target)
            if self._actives == 0:
                self.stop()

    def _is_active_watching(self, target):
        found = self._targets.get(target)
        if found is not None:
            for index in range(0, 3):
                for watcher in found[index].values():
                    active, _, _ = watcher
                    if active:
                        return True
        return False

    def _reset_watching(self, target, index, key, enable, disable):
        if not self._cleanup:
            found = self._targets.get(target)
            if found is not None:
                watcher = found[index].get(key)
                if watcher is not None:
                    active, _, disable_ = watcher
                    if active:
                        self._actives -= 1
                        disable_()
            else:
                self._targets[target] = [dict(), dict(), dict()]
            self._targets[target][index][key] = [True, enable, disable]
            self._actives += 1
            enable()
            return True
        return False

    def _release(self):
        if not self._cleanup:
            self._cleanup = True
            for target in tuple(self._targets):
                active = self._is_active_watching(target)
                self.release_watching(target)
                if active:
                    self._event_handler(target, self.CLEANUP)
            for signum in self._signal_pendings:
                self._signal_pendings[signum].clear()
            self._timer_pendings.clear()

    def _start_timeout(self, loop, secs, callback):
        def _callback():
            self._stop_timeout(loop, callback)
            callback()

        deadline = time.time() + secs
        self._stop_timeout(loop, callback)
        self._timer_pendings[callback] = loop.add_timeout(deadline, _callback)

    def _stop_timeout(self, loop, callback):
        timeout = self._timer_pendings.pop(callback, None)
        if timeout is not None:
            loop.remove_timeout(timeout)

    def _signal_handler(self, signum, frame):
        if signum in self._signal_pendings:
            for callback, loop in self._signal_pendings[signum].items():
                loop.add_callback_from_signal(callback)

    def _stop_signal(self, loop, signum, callback):
        if signum in self._signal_pendings:
            if callback in self._signal_pendings[signum]:
                self._signal_pendings[signum].pop(callback, None)

    def _start_signal(self, loop, signum, callback):
        if signum not in self._signal_pendings:
            self._signal_pendings[signum] = dict()
            signal.signal(signum, self._signal_handler)
        self._signal_pendings[signum][callback] = loop

    def _event_handler(self, target, events, payload=None):
        self.disable_watching(target)
        try:
            if target(events, payload):
                self.enable_watching(target)
        except Exception as exc:
            self.stop(exc)
        if self._actives == 0:
            self.stop()
