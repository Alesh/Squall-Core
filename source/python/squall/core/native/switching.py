import logging
from collections import deque
from collections.abc import Coroutine, Callable
from functools import partial

from squall.core.abc import Dispatcher as AbcDispatcher
from squall.core.abc import Future as AbcFuture
from squall.core.abc import Switcher as AbcSwitcher
from squall.core.native.futures import BaseFuture, FutureGroup

try:
    from squall.core.native.cb.tornado_ import EventLoop
except ImportError:
    from squall.core.native.cb.asyncio_ import EventLoop


class Switcher(AbcSwitcher):
    """ Coroutine switcher
    """

    def __init__(self):
        self._current = deque()

    @property
    def current(self) -> Coroutine:
        """ See more: `AbcSwitcher.current` """
        return self._current[0] if len(self._current) else None

    def switch(self, coro: Coroutine, value):
        """ See more: `AbcSwitcher.switch` """
        try:
            self._current.appendleft(coro)
            if isinstance(value, BaseException):  ### or issubclass(value, BaseException):
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


class SwitchedCoroutine(Coroutine):
    """ Switched coroutine
    """

    def __init__(self, switcher: Switcher,
                 setup: Callable = None, cancel: Callable = None):
        self._setup = setup
        self._cancel = cancel
        self._callback = partial(switcher.switch, switcher.current)

    def __next__(self):
        if self._setup is not None:
            value = self._setup(self._callback)
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
        if self._cancel is not None:
            self._cancel()
        super().throw(typ, val, tb)


class FuturedCoroutine(Coroutine, BaseFuture):
    """ Future-like coroutine
    """

    def __init__(self, disp, corofunc, *args, **kwargs):
        self._disp = disp
        self._coro = corofunc(disp, *args, **kwargs)
        assert isinstance(self._coro, Coroutine)
        BaseFuture.__init__(self)

    def __await__(self):
        return self._coro

    def send(self, value):
        """ See more: `Coroutine.send` """
        self._coro.send(value)

    def throw(self, typ, val=None, tb=None):
        """ See more: `Coroutine.throw` """
        if typ == GeneratorExit or isinstance(val, GeneratorExit):
            self._cancelled = True
        self._coro.send(typ, val, tb)

    def cancel(self):
        """ See more: `AbcFuture.exception` """
        if self.running():
            self._disp.switch(self._coro, GeneratorExit())
        return super().cancel()


class Dispatcher(AbcDispatcher, Switcher):
    """ Coroutine event dispatcher / switcher
    """

    def __init__(self):
        self._loop = EventLoop()
        Switcher.__init__(self)

    @property
    def READ(self):
        """ See more: `AbcDispatcher.READ` """
        return self._loop.READ

    @property
    def WRITE(self):
        """ See more: `AbcDispatcher.WRITE` """
        return self._loop.WRITE

    def spawn(self, corofunc, *args, **kwargs):
        """ See more: `AbcDispatcher.spawn` """
        coro = corofunc(self, *args, **kwargs)
        assert isinstance(coro, Coroutine)
        self.switch(coro, None)
        return coro

    def submit(self, corofunc, *args, **kwargs) -> AbcFuture:
        """ See more: `submit` """
        coro = FuturedCoroutine(self, corofunc, *args, **kwargs)
        assert isinstance(coro, Coroutine)
        self.switch(coro, None)
        return coro

    def start(self):
        """ See more: `AbcDispatcher.start` """
        return self._loop.start()

    def stop(self):
        """ See more: `AbcDispatcher.stop` """
        return self._loop.stop()

    def sleep(self, seconds=None):
        """ See more: `AbcDispatcher.sleep` """
        args = []
        seconds = seconds or 0
        seconds = seconds if seconds > 0 else 0
        assert isinstance(seconds, (int, float))

        def setup(callback):
            args.append(self._loop.setup_timeout(callback, seconds))

        def cancel():
            self._loop.cancel_timeout(*args)

        return SwitchedCoroutine(self, setup, cancel)

    def ready(self, fd, events, *, timeout=None):
        """ See more: `AbcDispatcher.ready` """
        args = []
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        assert isinstance(events, int) and events > 0
        assert events & (self.READ | self.WRITE) == events
        assert isinstance(fd, int) and fd > 0

        def setup(callback):
            timeout_exc = TimeoutError("I/O timeout")
            if timeout < 0:
                return timeout_exc
            args.append(self._loop.setup_ready(callback, fd, events))
            if timeout > 0:
                args.append(self._loop.setup_timeout(callback, timeout, timeout_exc))
            else:
                args.append(None)

        def cancel():
            if args:
                ready, timeout = args
                self._loop.cancel_ready(ready)
                if timeout is not None:
                    self._loop.cancel_timeout(timeout)

        return SwitchedCoroutine(self, setup, cancel)

    def signal(self, signum):
        """ See more: `AbcDispatcher.signal` """
        args = []
        signum = signum or 0
        assert isinstance(signum, int) and signum > 0

        def setup(callback):
            args.append(self._loop.setup_signal(callback, signum))

        def cancel():
            self._loop.cancel_signal(*args)

        return SwitchedCoroutine(self, setup, cancel)

    def wait(self, *futures, timeout=None):
        """ See more: `AbcDispatcher.wait` """
        args = []
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        assert len(futures) > 0

        if len(futures) == 1:
            future = futures[0]
        else:
            future = FutureGroup(futures)
        assert isinstance(future, AbcFuture)

        def setup(callback):
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
            args.append(future)
            if timeout > 0:
                args.append(self._loop.setup_timeout(callback, timeout, timeout_exc))
            else:
                args.append(None)

        def cancel():
            if args:
                future, timeout = args
                if future.running():
                    future.cancel()
                if timeout is not None:
                    self._loop.cancel_timeout(timeout)

        return SwitchedCoroutine(self, setup, cancel)
