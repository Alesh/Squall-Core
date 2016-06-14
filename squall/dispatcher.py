""" Event dispatcher based on tornado.
"""
import time
import signal
import logging

import tornado.log
import tornado.ioloop

tornado.log.enable_pretty_logging()
logger = logging.getLogger('squall')

READ = tornado.ioloop.IOLoop.READ
WRITE = tornado.ioloop.IOLoop.WRITE
ERROR = tornado.ioloop.IOLoop.ERROR
CLEANUP = 0x40000
TIMEOUT = 0x100
SIGNAL = 0x400


class _Dispatcher(object):

    _instance = None
    _timer_pendings = dict()
    _signal_pendings = dict()

    def __init__(self):
        self._exc = None
        self._actives = 0
        self._running = False
        self._cleanup = False
        self._targets = dict()
        self._loop = tornado.ioloop.IOLoop()

    @classmethod
    def _release(cls):
        self = cls.instance()
        if not self._cleanup:
            self._cleanup = True
            for target in tuple(self._targets):
                active = self._is_active_watching(target)
                self.release_watching(target)
                if active:
                    self._event_handler(target, CLEANUP)
            for signum in cls._signal_pendings:
                cls._signal_pendings[signum].clear()
            cls._timer_pendings.clear()
            cls._instance = None

    @classmethod
    def _start_timeout(cls, loop, secs, callback):
        def _callback():
            cls._timer_pendings.pop(callback)
            callback()

        deadline = time.time() + secs
        cls._stop_timeout(loop, callback)
        cls._timer_pendings[callback] = loop.add_timeout(deadline, _callback)

    @classmethod
    def _stop_timeout(cls, loop, callback):
        timeout = cls._timer_pendings.pop(callback, None)
        if timeout is not None:
            loop.remove_timeout(timeout)

    @classmethod
    def _signal_handler(cls, signum, frame):
        if signum in cls._signal_pendings:
            for callback, loop in cls._signal_pendings[signum].items():
                loop.add_callback_from_signal(callback)

    @classmethod
    def _stop_signal(cls, loop, signum, callback):
        if signum in cls._signal_pendings:
            if callback in cls._signal_pendings[signum]:
                cls._signal_pendings[signum].pop(callback, None)

    @classmethod
    def _start_signal(cls, loop, signum, callback):
        if signum not in cls._signal_pendings:
            cls._signal_pendings[signum] = dict()
            signal.signal(signum, cls._signal_handler)
        cls._signal_pendings[signum][callback] = loop

    def _event_handler(self, target, events):
        self.disable_watching(target)
        try:
            if target(events):
                self.enable_watching(target)
        except Exception as exc:
            self.stop(exc)

        if self._actives == 0:
            self.stop()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def start(cls):
        """ Starts event dispatching. """
        self = cls.instance()
        self._running = True
        try:
            self._loop.start()
        except KeyboardInterrupt:
            self._cleanup = True
            self._loop.stop()
        self._running = False
        exc = self._exc
        cls._release()
        if exc is not None:
            raise exc

    @classmethod
    def stop(cls, exc=None):
        """ Stops event dispatching. """
        if cls._instance is not None:
            self = cls._instance
            if self._running:
                self._exc = exc
                self._loop.add_callback(lambda: self._loop.stop())
            elif not self._cleanup:
                cls._release()
                if exc is not None:
                    raise exc

    def _is_active_watching(self, target):
        found = self._targets.get(target)
        if found is not None:
            for index in range(0, 3):
                watcher = found[index]
                if watcher is not None:
                    active, _, _ = watcher
                    if active:
                        return True
        return False

    def _reset_watching(self, target, index, enable, disable):
        if not self._cleanup:
            found = self._targets.get(target)
            if found is not None:
                watcher = found[index]
                if watcher is not None:
                    active, _, disable_ = watcher
                    if active:
                        self._actives -= 1
                        disable_()
            else:
                self._targets[target] = [None, None, None]
            self._targets[target][index] = [True, enable, disable]
            self._actives += 1
            enable()

    @classmethod
    def setup_wait_io(cls, target, fd, mask):
        """ Sets up I/O event watching. """
        self = cls.instance()

        def callback(_, events):
            self._event_handler(target, events)

        self._reset_watching(
            target, 0,
            lambda: self._loop.add_handler(fd, callback, mask),
            lambda: self._loop.remove_handler(fd))

    @classmethod
    def setup_wait(cls, target, secs):
        """ Sets up timeout watching. """
        self = cls.instance()

        def callback():
            self._event_handler(target, TIMEOUT)

        self._reset_watching(
            target, 1,
            lambda: cls._start_timeout(self._loop, secs, callback),
            lambda: cls._stop_timeout(self._loop, callback))

    @classmethod
    def setup_wait_signal(cls, target, signum):
        """ Sets up system sygnal watching. """
        self = cls.instance()

        def callback():
            self._event_handler(target, SIGNAL)

        self._reset_watching(
            target, 2,
            lambda: cls._start_signal(self._loop, signum, callback),
            lambda: cls._stop_signal(self._loop, signum, callback))

    @classmethod
    def disable_watching(cls, target):
        """ Disables all associated watching for given event target. """
        self = cls.instance()
        found = self._targets.get(target)
        if found is not None:
            for index in range(0, 3):
                watcher = found[index]
                if watcher is not None:
                    active, enable, disable = watcher
                    if active:
                        disable()
                        watcher[0] = False
                        self._actives -= 1
            return True
        return False

    @classmethod
    def enable_watching(cls, target):
        """ Enables all associated watching for given event target. """
        self = cls.instance()
        found = self._targets.get(target)
        if found is not None:
            for index in range(0, 3):
                watcher = found[index]
                if watcher is not None:
                    active, enable, disable = watcher
                    if not active:
                        enable()
                        watcher[0] = True
                        self._actives += 1
            return True
        return False

    @classmethod
    def release_watching(cls, target):
        """ Releases given event target and all associated watching. """
        if cls.disable_watching(target):
            self = cls.instance()
            self._targets.pop(target)
            if self._actives == 0:
                self.stop()


start = _Dispatcher.start
setup_wait = _Dispatcher.setup_wait
setup_wait_io = _Dispatcher.setup_wait_io
setup_wait_signal = _Dispatcher.setup_wait_signal
disable_watching = _Dispatcher.disable_watching
release_watching = _Dispatcher.release_watching
stop = _Dispatcher.stop
