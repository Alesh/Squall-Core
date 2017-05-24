""" Event-driven coroutine switching/dispatching
"""
import logging
from collections import deque
from concurrent.futures import CancelledError, Future
from squall.core_callback import EventLoop


class PartialFuture(NotImplementedError):
    def __init__(self):
        super().__init__("This is partial future-like implementation, "
                         "Use method `Dispatcher.complete` for take result")


class CannotSetupDispatcher(RuntimeError):
    def __init__(self, msg=None):
        super().__init__(msg or "Set up a dispatcher to event watching has fail")


class AsyncLet(object):
    """ Future-like wrapper that help to manage coroutines into a Squall environment.
    """
    def __init__(self, corofunc, disp, *args, **kwargs):
        self._disp = disp
        self._running = True
        self._cancelled = False
        self._done_callbacks = list()
        self._result = self._exception = None
        self._coro = corofunc(disp, *args, **kwargs)
        self.switch(None)  # start coroutine

    def __repr__(self):
        msg = '<{} at {:#x} state={{}}>'.format(self.__class__.__name__, id(self))
        if self._running:
            return msg.format('running')
        if self._cancelled:
            return msg.format('cancelled')
        msg = msg.format('finished and {} {}')
        if self._exception:
            return msg.format('raised', self._exception)
        return msg.format('returned', self._result)

    def _invoke_callbacks(self):
        for callback in self._done_callbacks:
            try:
                callback(self)
            except Exception:
                logging.exception("Exception when calling done callback for %s", self)

    def running(self):
        """ Returns True if wrapped coroutine is currently running. """
        return self._running

    def cancelled(self):
        """ Returns True if wrapped coroutine has been cancelled. """
        return self._cancelled

    def done(self):
        """ Returns True if wrapped coroutine has finished with result. """
        return not self._cancelled and not self._running

    def switch(self, value):
        """ Sends some value into wrapped coroutine to switches its running back.
        """
        try:
            self._disp._stack.appendleft(self)
            if isinstance(value, BaseException):
                self._coro.throw(value)
            else:
                self._coro.send(value)
        except BaseException as exc:
            self._running = False
            if isinstance(exc, StopIteration):
                self._result = exc.value
            else:
                if isinstance(exc, GeneratorExit):
                    self._cancelled = True
                else:
                    self._exception = exc
                    logging.exception("Uncaught exception when switch(%s, %s)", self._coro, value)
            self._invoke_callbacks()
        finally:
            self._disp._stack.popleft()

    def result(self, timeout=None):
        """ If wrapped coroutine has finished succeeded
        returns its result or raises exception otherwise.
        """
        if self._cancelled:
            raise CancelledError()
        if self._running:
            self.cancel()
            raise PartialFuture()
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self, timeout=None):
        """ If wrapped coroutine fail, returns exception or `None`.
        """
        if self._cancelled:
            raise CancelledError()
        if self._running:
            self.cancel()
            raise PartialFuture()
        return self._exception

    def cancel(self):
        """ Cancel wrapped coroutine.
        """
        if not self.done():
            self.switch(GeneratorExit())
        return self._cancelled

    def add_done_callback(self, callback):
        """ Attaches the given `callback` to this as done callback.
        """
        self._done_callbacks.append(callback)


class Awaitable(object):
    """ Specialized base class for awaitable objects to using into a Squall environment.
    """
    def __init__(self, disp, *args):
        self._args = args
        self._loop = disp._loop
        self._callback = disp.current.switch

    def __await__(self):
        """ Makes it awaitable. """
        return self

    def __next__(self):
        """ Prepared this awaitable to going awaiting mode. """
        early_event, *args = self._setup(*self._args)
        self._args = args
        if early_event is not None:
            self._cancel(*self._args)
            # event already occurred, no need awaiting
            if isinstance(early_event, BaseException):
                raise early_event
            else:
                raise StopIteration(early_event)

    def _setup(self, *args):
        """ Called to setup an event watching for this awaitable.

        Returns:
            early_event: event if it already occurred, otherwise `None`.
            *args: Possible parameters for calling `self._cancel`.
        """
    def _cancel(self, *args):
        """ Called to cancel an event watching for this awaitable. """

    def send(self, value):
        """ Called when awaitable received result to set. """
        self.throw(StopIteration(value))

    def throw(self, *exc_info):
        """ Called when awaitable received exception to raise. """
        self._cancel(*self._args)
        if len(exc_info) == 1:
            raise exc_info[0]
        else:
            exc = exc_info[1]
            if len(exc_info) == 3:
                exc = exc.with_traceback(exc_info[2])
        raise exc


class Dispatcher(object):
    """ Coroutine switcher/dispatcher
    """

    def __init__(self):
        self._stack = deque()
        self._loop = EventLoop()

    @property
    def READ(self):
        """ Event code I/O ready to read. """
        return self._loop.READ

    @property
    def WRITE(self):
        """ Event code I/O ready to write. """
        return self._loop.WRITE

    @property
    def current(self):
        """ Return current running `AsyncLet` instance. """
        return self._stack[0] if self._stack else None

    def submit(self, corofunc, *args, **kwargs):
        """ Creates the wrapped coroutine and submits to execute. """
        return AsyncLet(corofunc, self, *args, **kwargs)

    def start(self):
        """ Starts the coroutine dispatching. """
        return self._loop.start()

    def stop(self):
        """ Stops a coroutine dispatching
        """
        return self._loop.stop()

    def sleep(self, seconds=None):
        """ Returns the awaitable that switches current coroutine back
        after `seconds` or at next loop if `seconds` is `None`.

        Raises:
            IOError: if failed event loop
        """
        seconds = seconds or 0
        seconds = seconds if seconds > 0 else 0
        assert isinstance(seconds, (int, float))
        return _SleepAwaitable(self, seconds)

    def ready(self, fd, events, *, timeout=None):
        """ Returns the awaitable that switches current coroutine back
        when I/O device with a given `fd` ready to read and/or write.

        Raises:
            IOError: if failed event loop
            TimeoutError: if `timeout` is set and elapsed.
        """
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        assert isinstance(events, int) and (events & (self.READ | self.WRITE) == events)
        assert isinstance(fd, int) and fd >= 0
        return _ReadyAwaitable(self, fd, events, timeout)

    def signal(self, signum):
        """ Returns the awaitable that switches current coroutine back
        when received the system signal with a given `signum`.

        Raises:
            IOError: if failed event loop
        """
        signum = signum or 0
        assert isinstance(signum, int) and signum > 0
        return _SignalAwaitable(self, signum)

    def complete(self, *futures, timeout=None):
        """ Returns the awaitable that switches current coroutine back
        when the given future-like or list of future-like objects has done.

        Raises:
            IOError: if failed event loop
            TimeoutError: `timeout` is set and elapsed.
        """
        timeout = timeout or 0
        timeout = timeout if timeout >= 0 else -1
        assert isinstance(timeout, (int, float))
        assert len(futures) > 0
        assert all(isinstance(item, (AsyncLet, Future)) for item in futures)
        return _CompleteAwaitable(self, futures, timeout)


class _SleepAwaitable(Awaitable):
    """ Awaitable that returns `Dispatcher.sleep`
    """

    def _setup(self, seconds):
        timeout_handle = self._loop.setup_timer(self._callback, seconds)
        if timeout_handle is None:
            return CannotSetupDispatcher(),
        return None, timeout_handle

    def _cancel(self, timeout_handle=None):
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)

    def throw(self, exc, *args):
        if isinstance(exc, TimeoutError):
            # exception `TimeoutError` has got as an event message is normal for this awaitable
            raise StopIteration(True)
        super().throw(exc, *args)


class _ReadyAwaitable(Awaitable):
    """ Awaitable that returns `Dispatcher.sleep`
    """

    def _setup(self, fd, events, timeout):
        timeout_handle = None
        if timeout < 0:
            return TimeoutError("I/O timeout"),
        elif timeout > 0:
            timeout_handle = self._loop.setup_timer(self._callback, timeout)
            if timeout_handle is None:
                return CannotSetupDispatcher(),
        ready_handle = self._loop.setup_io(self._callback, fd, events)
        if ready_handle is None:
            return CannotSetupDispatcher(), None, timeout_handle
        return None, ready_handle, timeout_handle

    def _cancel(self, ready_handle=None, timeout_handle=None):
        if ready_handle is not None:
            self._loop.cancel_io(ready_handle)
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)


class _SignalAwaitable(Awaitable):
    """ Awaitable that returns `Dispatcher.signal`
    """

    def _setup(self, signum):
        signal_handle = self._loop.setup_signal(self._callback, signum)
        if signal_handle is None:
            return CannotSetupDispatcher(),
        return None, signal_handle

    def _cancel(self, signal_handle=None):
        if signal_handle is not None:
            self._loop.cancel_signal(signal_handle)


class _CompleteAwaitable(Awaitable):
    """ Awaitable that returns `Dispatcher.complete`
    """

    def __init__(self, disp, futures, timeout):
        self._futures = futures
        super().__init__(disp, timeout)

    def _one_complete(self, _):
        if all(future.done() or future.cancelled() for future in self._futures):
            self._callback(tuple(future for future in self._futures))

    def _setup(self, timeout):
        timeout_handle = None
        if timeout < 0:
            return TimeoutError("I/O timeout"),
        elif timeout > 0:
            timeout_handle = self._loop.setup_timer(self._callback, timeout)
            if timeout_handle is None:
                return CannotSetupDispatcher(),
        for future in self._futures:
            future.add_done_callback(self._one_complete)
        return None, timeout_handle

    def _cancel(self, timeout_handle=None):
        if timeout_handle is not None:
            self._loop.cancel_timer(timeout_handle)
        for future in self._futures:
            future.cancel()
