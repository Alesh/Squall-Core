import logging
from collections.abc import Coroutine, Callable
from functools import partial


class CoroutineSwitcher(object):
    """ Coroutine switcher
    """

    def __init__(self):
        self._current = None

    @property
    def current(self) -> Coroutine:
        return self._current

    def switch(self, coro: Coroutine, value):
        try:
            self._current = coro
            if isinstance(value, BaseException):
                coro.throw(value)
            else:
                coro.send(value)
            return True
        except BaseException as exc:
            if not isinstance(exc, (StopIteration, GeneratorExit)):
                logging.exception("Uncaught exception when switch({}, {})"
                                  "".format(coro, value))
        finally:
            self._current = None
        return False

    def close(self, coro):
        self.switch(coro, GeneratorExit())


class SwitchedCoroutine(Coroutine):
    """ Switched coroutine
    """

    def __init__(self, switcher: CoroutineSwitcher,
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
        self.throw(StopIteration(value))

    def throw(self, typ, val=None, tb=None):
        if self._cancel is not None:
            self._cancel()
        super().throw(typ, val, tb)
