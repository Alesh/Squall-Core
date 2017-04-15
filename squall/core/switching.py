""" Coroutine switching
"""
import logging
import threading
from time import time
from collections import deque
from concurrent.futures import CancelledError, Future
from collections.abc import Coroutine as AbcCoroutine


try:
    from squall.core_cython import EventLoop
except ImportError:
    from squall.core_fallback import EventLoop

_TLS = threading.local()


class _Coroutine(object):
    """ Future-like coroutine implementation
    with a mostly-compatible `concurrent.futures.Future`.
    """
    def __init__(self, corofunc, disp, *args, **kwargs):
        self.__result = None
        self.__running = True
        self.__exception = None
        self.__cancelled = False
        self.__done_callbacks = list()
        self.__coro = corofunc(disp, *args, **kwargs)
        assert isinstance(self.__coro, AbcCoroutine)
        self.switch(None)  # Start coroutine

    def __repr__(self):
        cls_name = self.__class__.__name__
        state = 'running' if self.running() else 'cancelled' if self.cancelled() else 'finished'
        if self.done():
            if self.__exception:
                return ('<{} at {:#x} state={} raised {}>'
                        ''.format(cls_name, id(self), state, self.__exception.__class__.__name__))
            return ('<{} at {:#x} state={} returned {}>'
                    ''.format(cls_name, id(self), state, self.__result.__class__.__name__))
        return '<{} at {:#x} state={}>'.format(cls_name, id(self), state)

    def running(self):
        """ Returns True if this coroutine is currently running.
        """
        return self.__running and not self.__cancelled

    def cancelled(self):
        """ Returns True if this coroutine has been cancelled.
        """
        return self.__cancelled

    def done(self):
        """ Returns True if this coroutine has finished with result.
        """
        return self.__cancelled or (not self.__running)

    class NotFullyImplemented(NotImplementedError):
        def __init__(self):
            super().__init__("Use method `Dispatcher.complete` for take "
                             "a result of uncompleted future-like coroutine")

    def result(self, timeout=None):
        """ If this coroutine has finished succeeded returns its result
         or raises exception otherwise.
        """
        if self.cancelled():
            raise CancelledError()
        if self.running():
            self.cancel()
            raise self.NotFullyImplemented()
        if self.__exception is not None:
            raise self.__exception
        return self.__result

    def exception(self, timeout=None):
        """ If this coroutine fail, returns exception or `None`.
        """
        if self.cancelled():
            raise CancelledError()
        if self.running():
            self.cancel()
            raise self.NotFullyImplemented()
        return self.__exception

    @classmethod
    def current(cls):
        """ Return current coroutine.
        """
        coro_stack = _TLS.__dict__.setdefault('coro_stack', deque())
        return coro_stack[0] if len(coro_stack) else None

    def switch(self, value):
        """ Sends some value into coroutine to switches its running back.
        """
        coro_stack = _TLS.__dict__.setdefault('coro_stack', deque())
        try:
            coro_stack.appendleft(self)
            if isinstance(value, BaseException):
                self.__coro.throw(value)
            else:
                self.__coro.send(value)
        except BaseException as exc:
            self.__running = False
            if isinstance(exc, StopIteration):
                self.__result = exc.value
            else:
                if isinstance(exc, GeneratorExit):
                    self.__cancelled = True
                else:
                    self.__exception = exc
                    logging.exception("Uncaught exception when switch({}, {})"
                                      "".format(self.__coro, value))
            self._invoke_callbacks()
        finally:
            coro_stack.popleft()

    def add_done_callback(self, callback):
        """ Attaches the given `callback` to this coroutine.
        """
        self.__done_callbacks.append(callback)

    def cancel(self):
        """ Cancel this coroutine.
        """
        if not self.done():
            self.switch(GeneratorExit())
        return self.__cancelled

    def _invoke_callbacks(self):
        for callback in self.__done_callbacks:
            try:
                callback(self)
            except Exception:
                logging.exception('Exception when calling callback for %r', self)


class _Awaitable(AbcCoroutine):
    """ Base class for `awaitable` implementation.
    """
    def __init__(self, *args):
        self._args = args
        self._callback = _Coroutine.current().switch

    def setup(self, *args):
        """ Called to setup event watching """

    def cancel(self, *args):
        """ Called to cancel event watching """

    def __next__(self):
        early_value, *args = self.setup(*self._args)
        self._args = args
        if early_value is not None:
            if isinstance(early_value, BaseException):
                raise early_value
            else:
                raise StopIteration(early_value)

    def __await__(self):
        return self

    def send(self, value):
        """ Called when awaitable received to set result. """
        self.throw(StopIteration(value))

    def throw(self, typ, val=None, tb=None):
        """ Called when awaitable received to raise exception. """
        self.cancel(*self._args)
        super().throw(typ, val, tb)


class EventLoopError(IOError):
    def __init__(self, msg=None):
        super().__init__(msg or "Event loop error")


class CannotSetupWatching(RuntimeError):
    def __init__(self, msg=None):
        super().__init__(msg or "Cannot setup event watching")


class Dispatcher(object):
    """ Coroutine switcher/dispatcher
    """

    def __init__(self):
        self._loop = EventLoop()

    @property
    def READ(self):
        """ Event code I/O ready to read.
        """
        return self._loop.READ

    @property
    def WRITE(self):
        """ Event code I/O ready to write.
        """
        return self._loop.WRITE

    def submit(self, corofunc, *args, **kwargs):
        """ Creates the coroutine and submits to execute.
        """
        return _Coroutine(corofunc, self, *args, **kwargs)

    def start(self):
        """ Starts the coroutine dispatching.
        """
        return self._loop.start()

    def stop(self):
        """ Stops a coroutine dispatching
        """
        return self._loop.stop()

    def sleep(self, seconds=None):
        """ Returns the awaitable that switches current coroutine back
        after `seconds` or at next loop if `seconds` is `None`.
        """
        seconds = seconds or 0
        assert isinstance(seconds, (int, float))
        seconds = seconds if seconds > 0 else 0
        return _SleepAwaitable(self._loop, seconds)

    def ready(self, fd, events, *, timeout=None):
        """ Returns the awaitable that switches current coroutine back
        when I/O device with a given `fd` ready to read and/or write.

        Raises:
            TimeoutError: if `timeout` is set and elapsed.
        """
        timeout = timeout or 0
        assert isinstance(timeout, (int, float))
        assert isinstance(events, int) and events > 0
        assert events & (self.READ | self.WRITE) == events
        assert isinstance(fd, int) and fd >= 0
        timeout = timeout if timeout >= 0 else -1
        return _ReadyAwaitable(self._loop, fd, events, timeout)

    def signal(self, signum):
        """ Returns the awaitable that switches current coroutine back
        when received the system signal with a given `signum`.
        """
        signum = signum or 0
        assert isinstance(signum, int) and signum > 0
        return _SignalAwaitable(self._loop, signum)

    def complete(self, *futures, timeout=None):
        """ Returns the awaitable that switches current coroutine back
        when the given future-like or list of future-like objects has done.

        Raises:
            TimeoutError: `timeout` is set and elapsed.
        """
        timeout = timeout or 0
        assert len(futures) > 0
        assert isinstance(timeout, (int, float))
        timeout = timeout if timeout >= 0 else -1
        assert all(isinstance(item, (_Coroutine, Future)) for item in futures)
        return _СompleteAwaitable(self._loop, futures, timeout)


class _SleepAwaitable(_Awaitable):
    """ Creates and returns awaitable for `Dispatcher.sleep`
    """
    def __init__(self, loop, seconds):
        self._loop = loop
        super().__init__(seconds)

    def _on_event(self, revents):
        if revents == self._loop.TIMEOUT:
            self._callback(True)
        else:
            self._callback(EventLoopError())

    def setup(self, seconds):
        handle = self._loop.setup_timer(self._on_event, seconds)
        if handle is None:
            return CannotSetupWatching(),
        return None, handle

    def cancel(self, handle):
        self._loop.cancel_timer(handle)


class _ReadyAwaitable(_Awaitable):
    """ Creates and returns awaitable for `Dispatcher.ready`
    """
    def __init__(self, loop, fd, events, timeout):
        self._loop = loop
        super().__init__(fd, events, timeout)

    def _on_event(self, revents):
        if revents & (self._loop.READ | self._loop.WRITE) == revents:
            self._callback(revents)
        elif revents == self._loop.TIMEOUT:
            self._callback(TimeoutError("I/O timeout"))
        else:
            self._callback(EventLoopError())

    def setup(self, fd, events, timeout):
        if timeout < 0:
            return TimeoutError("I/O timeout"),
        timeout_handle = None
        ready_handle = self._loop.setup_io(self._on_event, fd, events)
        if ready_handle is not None:
            if timeout > 0:
                timeout_handle = self._loop.setup_timer(self._on_event, timeout)
                if timeout_handle is None:
                    self._loop.cancel_io(ready_handle)
                    return CannotSetupWatching(),
            return None, ready_handle, timeout_handle
        return CannotSetupWatching(),

    def cancel(self, ready_handle, timeout_handle):
        self._loop.cancel_io(ready_handle)
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)


class _SignalAwaitable(_Awaitable):
    """ Creates and returns awaitable for `Dispatcher.signal`
    """
    def __init__(self, loop, signum):
        self._loop = loop
        super().__init__(signum)

    def _on_event(self, revents):
        if revents == self._loop.SIGNAL:
            self._callback(True)
        else:
            self._callback(EventLoopError())

    def setup(self, signum):
        handle = self._loop.setup_signal(self._on_event, signum)
        if handle is None:
            return CannotSetupWatching(),
        return None, handle

    def cancel(self, handle):
        self._loop.cancel_signal(handle)


class _СompleteAwaitable(_Awaitable):
    """ Creates and returns awaitable for `Dispatcher.complete`
    """
    def __init__(self, loop, futures, timeout):
        self._loop = loop
        self._futures = futures
        super().__init__(timeout)

    def _on_event(self, revents):
        if isinstance(revents, tuple):
            self._callback(revents)
        else:
            self._cancel_all()
            if revents == self._loop.TIMEOUT:
                self._callback(TimeoutError("I/O timeout"))
            else:
                self._callback(EventLoopError())

    def _done_callback(self, future):
        if all(future.done() for future in self._futures):
            self._on_event(tuple(future for future in self._futures))

    def _cancel_all(self):
        for future in self._futures:
            future.cancel()

    def setup(self, timeout):
        if timeout < 0:
            return TimeoutError("I/O timeout"),

        timeout_handle = None
        if timeout > 0:
            timeout_handle = self._loop.setup_timer(self._on_event, timeout)
            if timeout_handle is None:
                return CannotSetupWatching(),
        for future in self._futures:
            future.add_done_callback(self._done_callback)
        return None, timeout_handle

    def cancel(self, timeout_handle):
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)
        self._cancel_all()


# Utilites


class timeout_gen(object):
    """ Timeout generator
    """

    def __init__(self, initial_timeout):
        assert (isinstance(initial_timeout, (int, float)) or
                initial_timeout is None)
        self.deadline = None
        if initial_timeout is not None:
            self.deadline = time() + initial_timeout

    def __iter__(self):
        return self

    def __next__(self):
        if self.deadline is not None:
            value = self.deadline - time()
            return value if value > 0 else -1
