import logging
from collections import deque
from collections.abc import Coroutine
from functools import partial

from squall.core.abc import Dispatcher as AbcDispatcher
from squall.core.abc import Future as AbcFuture
from squall.core.native.futures import FuturedCoroutine, FutureGroup

try:
    from squall.core.native.cb.tornado_ import EventLoop
except ImportError:
    from squall.core.native.cb.asyncio_ import EventLoop


class SwitchedCoroutine(Coroutine):
    """ Switched coroutine
    """

    def __init__(self, disp: AbcDispatcher, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        self._callback = partial(disp.switch, disp.current)

    def setup(self, callback, *args, **kwargs):
        """ Called to setup event watching """

    def cancel(self):
        """ Called to cancel event watching """

    def __next__(self):
        value = self.setup(self._callback, *self._args, **self._kwargs)
        if value is not None:
            if isinstance(value, BaseException):
                self.throw(value)
            else:
                self.throw(StopIteration(value))

    def __await__(self):
        return self

    def send(self, value):
        """ Called when coroutine received some value. """
        self.throw(StopIteration(value))

    def throw(self, typ, val=None, tb=None):
        """ Called when coroutine received request to raise exception. """
        self.cancel()
        super().throw(typ, val, tb)


class Dispatcher(AbcDispatcher):
    """ Coroutine event dispatcher / switcher
    """

    def __init__(self):
        self._current = deque()
        self._loop = EventLoop()

    @property
    def READ(self):
        """ See more: `AbcDispatcher.READ` """
        return self._loop.READ

    @property
    def WRITE(self):
        """ See more: `AbcDispatcher.WRITE` """
        return self._loop.WRITE

    @property
    def current(self) -> Coroutine:
        """ See more: `AbcDispatcher.current` """
        return self._current[0] if len(self._current) else None

    def spawn(self, corofunc, *args, **kwargs):
        """ See more: `AbcDispatcher.spawn` """
        coro = corofunc(self, *args, **kwargs)
        assert isinstance(coro, Coroutine)
        self.switch(coro, None)
        return coro

    def submit(self, corofunc, *args, **kwargs) -> AbcFuture:
        """ See more: `AbcDispatcher.submit` """
        coro = FuturedCoroutine(self, corofunc, *args, **kwargs)
        assert isinstance(coro, Coroutine)
        self.switch(coro, None)
        return coro

    def switch(self, coro: Coroutine, value):
        """ See more: `AbcDispatcher.switch` """
        try:
            self._current.appendleft(coro)
            if isinstance(value, BaseException):
                coro.throw(value)
            elif isinstance(value, type) and issubclass(value, BaseException):
                coro.throw(value)
            else:
                coro.send(value)
            return (None, None)
        except BaseException as exc:
            if not isinstance(exc, (StopIteration, GeneratorExit)):
                logging.exception("Uncaught exception when switch({}, {})"
                                  "".format(coro, value))
            elif isinstance(exc, StopIteration):
                if isinstance(coro, FuturedCoroutine):
                    coro.set_result(exc.value)
                return (exc.value, exc)
            if isinstance(coro, FuturedCoroutine):
                coro.set_exception(exc)
            return (None, exc)
        finally:
            self._current.popleft()

    def start(self):
        """ See more: `AbcDispatcher.start` """
        return self._loop.start()

    def stop(self):
        """ See more: `AbcDispatcher.stop` """
        return self._loop.stop()

    def sleep(self, seconds=None):
        """ See more: `AbcDispatcher.sleep` """
        return _SleepCoroutine(self, seconds)

    def ready(self, fd, events, *, timeout=None):
        """ See more: `AbcDispatcher.ready` """
        return _ReadyCoroutine(self, fd, events, timeout)

    def signal(self, signum):
        """ See more: `AbcDispatcher.signal` """
        return _SignalCoroutine(self, signum)

    def wait(self, *futures, timeout=None):
        """ See more: `AbcDispatcher.wait` """
        return _WaitCoroutine(self, futures, timeout)


class _SleepCoroutine(SwitchedCoroutine):
    """ Awaitable for `Dispatcher.sleep` """

    def __init__(self, disp, seconds):
        self._handles = []
        self._loop = disp._loop
        seconds = seconds or 0
        seconds = seconds if seconds > 0 else 0
        assert isinstance(seconds, (int, float))
        super().__init__(disp, seconds)

    def setup(self, callback, seconds):
        self._handles.append(self._loop.setup_timeout(callback, seconds))

    def cancel(self):
        if self._handles:
            self._loop.cancel_timeout(*self._handles)


class _ReadyCoroutine(SwitchedCoroutine):
    """ Awaitable for `Dispatcher.ready` """

    def __init__(self, disp, fd, events, timeout):
        self._handles = []
        self._loop = disp._loop
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        assert isinstance(events, int) and events > 0
        assert events & (disp.READ | disp.WRITE) == events
        assert isinstance(fd, int) and fd > 0
        super().__init__(disp, fd, events, timeout)

    def setup(self, callback, fd, events, timeout):
        timeout_exc = TimeoutError("I/O timeout")
        if timeout < 0:
            return timeout_exc
        self._handles.append(self._loop.setup_ready(callback, fd, events))
        if timeout > 0:
            self._handles.append(self._loop.setup_timeout(callback, timeout, timeout_exc))
        else:
            self._handles.append(None)

    def cancel(self):
        if self._handles:
            ready, timeout = self._handles
            self._loop.cancel_ready(ready)
            if timeout is not None:
                self._loop.cancel_timeout(timeout)


class _SignalCoroutine(SwitchedCoroutine):
    """ Awaitable for `Dispatcher.signal` """

    def __init__(self, disp, signum):
        self._handles = []
        self._loop = disp._loop
        signum = signum or 0
        assert isinstance(signum, int) and signum > 0
        super().__init__(disp, signum)

    def setup(self, callback, signum):
        self._handles.append(self._loop.setup_signal(callback, signum))

    def cancel(self):
        if self._handles:
            self._loop.cancel_signal(*self._handles)


class _WaitCoroutine(SwitchedCoroutine):
    """ Awaitable for `Dispatcher.wait` """

    def __init__(self, disp, futures, timeout):
        self._handles = []
        self._loop = disp._loop
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        assert len(futures) > 0
        if len(futures) == 1:
            future = futures[0]
        else:
            future = FutureGroup(futures)
        assert isinstance(future, AbcFuture)
        super().__init__(disp, future, timeout)

    def setup(self, callback, future, timeout):
        timeout_exc = TimeoutError("I/O timeout")
        if timeout < 0:
            return timeout_exc
        if future.done():
            try:
                result = future.result()
                return result if result is not None else True
            except BaseException as exc:
                return exc

        def done_callback(future):
            try:
                result = future.result()
                callback(result if result is not None else True)
            except BaseException as exc:
                callback(exc)

        future.add_done_callback(done_callback)
        self._handles.append(future)
        if timeout > 0:
            self._handles.append(self._loop.setup_timeout(callback, timeout, timeout_exc))
        else:
            self._handles.append(None)

    def cancel(self):
        if self._handles:
            future, timeout = self._handles
            if future.running():
                future.cancel()
            if timeout is not None:
                self._loop.cancel_timeout(timeout)
