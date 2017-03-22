import logging
from abc import abstractmethod
from concurrent.futures import CancelledError

from squall.core.abc import Coroutine, Future as AbcFuture


class BaseFuture(AbcFuture):
    """ Base of future-like objects
    """

    def __init__(self):
        self._running = True
        self._cancelled = False
        self._done_callbacks = list()
        self._exception = None
        self._result = None

    def _state(self):
        if self.running():
            return 'running'
        elif self.cancelled():
            return 'cancelled'
        else:
            return 'finished'

    def __repr__(self):
        if self.done():
            if self._exception:
                return '<%s at %#x state=%s raised %s>' % (
                    self.__class__.__name__,
                    id(self), self._state(),
                    self._exception.__class__.__name__)
            else:
                return '<%s at %#x state=%s returned %s>' % (
                    self.__class__.__name__,
                    id(self), self._state(),
                    self._result.__class__.__name__)
        return '<%s at %#x state=%s>' % (
            self.__class__.__name__,
            id(self), self._state())

    def running(self):
        """ See for detail `AbcFuture.running` """
        return self._running and not self._cancelled

    def cancelled(self):
        """ See for detail `AbcFuture.cancelled` """
        return self._cancelled

    def done(self):
        """ See for detail `AbcFuture.done` """
        return self._cancelled or (not self._running)

    @abstractmethod
    def cancel(self):
        """ See for detail `AbcFuture.exception` """
        self._cancelled = True
        return self.cancelled()

    def exception(self, timeout=None):
        """ See for detail `AbcFuture.exception` """
        if self.cancelled():
            raise CancelledError()
        if self.running():
            self.cancel()
            raise NotImplementedError("Use method `Dispatcher.complete` for take "
                                      "a result of uncompleted future-like coroutine.")
        return self._exception

    def result(self, timeout=None):
        """ See for detail `AbcFuture.result` """
        if self.cancelled():
            raise CancelledError()
        if self.running():
            self.cancel()
            raise NotImplementedError("Use method `Dispatcher.complete` for take "
                                      "a result of uncompleted future-like coroutine.")
        if self._exception is not None:
            raise self._exception
        return self._result

    def add_done_callback(self, callback):
        """ See for detail `AbcFuture.add_done_callback` """
        self._done_callbacks.append(callback)

    def set_result(self, result):
        """ Sets result and done """
        if self.running():
            self._running = False
            self._result = result
            self._invoke_callbacks()

    def set_exception(self, exc):
        """ Sets exception and done """
        if self.running():
            self._running = False
            self._exception = exc
            self._invoke_callbacks()

    def _invoke_callbacks(self):
        for callback in self._done_callbacks:
            try:
                callback(self)
            except Exception:
                logging.exception('exception calling callback for %r', self)


class FutureGroup(BaseFuture):
    """ Future group
    """

    def __init__(self, futures):
        super().__init__()
        self._futures = dict()
        assert isinstance(futures, (tuple, list))
        assert all([isinstance(future, AbcFuture) for future in futures])

        def callback(future):
            if future in self._futures:
                try:
                    result = future.result()
                    self._futures[future][0] = True
                    self._futures[future][1] = result
                except BaseException as exc:
                    self._futures[future][0] = False
                    self._futures[future][1] = exc

            if all([finish is not None for finish, _ in self._futures.values()]):
                self.set_result(tuple(result for _, result in self._futures.values()))

        for future in futures:
            self._futures[future] = [None, None]
            future.add_done_callback(callback)

    def cancel(self):
        """ See for detail `AbcFuture.exception` """
        if self.running():
            for future in self._futures.keys():
                future.cancel()
        return super().cancel()


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
        """ See for detail `Coroutine.send` """
        self._coro.send(value)

    def throw(self, typ, val=None, tb=None):
        """ See for detail `Coroutine.throw` """
        if typ == GeneratorExit or isinstance(val, GeneratorExit):
            self._cancelled = True
        self._coro.throw(typ, val, tb)

    def cancel(self):
        """ See for detail `AbcFuture.exception` """
        if self.running():
            self._disp.switch(self._coro, GeneratorExit)
        return super().cancel()
