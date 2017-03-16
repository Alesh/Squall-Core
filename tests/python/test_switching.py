import logging

import pytest
from squall.core.native.switching import Dispatcher
from squall.core.native.switching import SwitchedCoroutine as BaseSwitchedCoroutine


@pytest.yield_fixture
def callog():
    _callog = list()
    yield _callog


class MockSwitcher(Dispatcher):
    """ Mock coroutine switcher """

    def __init__(self, callog):
        self._callog = callog
        super().__init__()

    def switch(self, coro, value):
        """ Implementation of `Switcher.switch` """
        result = super().switch(coro, value)
        value = type(value) if isinstance(value, BaseException) else value
        result, exc = result
        self._callog.append(('switch', value, exc is None))


class SwitchedCoroutine(BaseSwitchedCoroutine):
    def __init__(self, disp, setup, cancel):
        self._setup = setup
        self._cancel = cancel
        super().__init__(disp)

    def setup(self, callback):
        return self._setup(callback)

    def cancel(self):
        self._cancel()


async def async1func(switcher, callog,
                     setup=None, cancel=None,
                     catch_exception=False):
    result = None
    if catch_exception:
        try:
            result = await SwitchedCoroutine(switcher, setup, cancel)
        except Exception as exc:
            callog.append(('catch', type(exc)))
    else:
        result = await SwitchedCoroutine(switcher, setup, cancel)
    callog.append(('result', result))
    return result


def test_SwitchedCoroutine_switch(callog):
    switcher = MockSwitcher(callog)
    coro = async1func(switcher, callog,
                      lambda *args: callog.append('setup'),
                      lambda *args: callog.append('cancel'))
    switcher.switch(coro, None)
    switcher.switch(coro, 100)

    print(callog)
    assert callog == ['setup', ('switch', None, True),
                      'cancel', ('result', 100), ('switch', 100, False)]


def test_SwitchedCoroutine_close(callog):
    switcher = MockSwitcher(callog)
    coro = async1func(switcher, callog,
                      lambda *args: callog.append('setup'),
                      lambda *args: callog.append('cancel'))
    switcher.switch(coro, None)
    switcher.switch(coro, GeneratorExit())

    print(callog)
    assert callog == ['setup', ('switch', None, True),
                      'cancel', ('switch', GeneratorExit, False)]


def test_SwitchedCoroutine_caught(callog):
    switcher = MockSwitcher(callog)
    coro = async1func(switcher, callog,
                      lambda *args: callog.append('setup'),
                      lambda *args: callog.append('cancel'),
                      catch_exception=True)
    switcher.switch(coro, None)
    exc = ValueError("Sample exception")
    switcher.switch(coro, exc)

    print(callog)
    assert callog == ['setup', ('switch', None, True),
                      'cancel', ('catch', ValueError), ('result', None), ('switch', ValueError, False)]


def test_SwitchedCoroutine_uncaught(callog, caplog):
    switcher = MockSwitcher(callog)
    coro = async1func(switcher, callog,
                      lambda *args: callog.append('setup'),
                      lambda *args: callog.append('cancel'),
                      catch_exception=False)
    with caplog.at_level(logging.ERROR):
        switcher.switch(coro, None)
        exc = ValueError("sample exception")
        switcher.switch(coro, exc)

    assert len(caplog.records) == 1
    for record in caplog.records:
        exc = record.exc_info[1]
        assert isinstance(exc, ValueError)
        assert str(exc) == "sample exception"

    print(callog)
    assert callog == ['setup', ('switch', None, True), 'cancel', ('switch', ValueError, False)]


def test_SwitchedCoroutine_set_in_setup(callog, caplog):
    switcher = MockSwitcher(callog)
    coro = async1func(switcher, callog,
                      lambda *args: callog.append('setup') or 500,
                      lambda *args: callog.append('cancel'))

    with caplog.at_level(logging.ERROR):
        switcher.switch(coro, None)
        switcher.switch(coro, 100)
    assert len(caplog.records) == 1
    for record in caplog.records:
        exc = record.exc_info[1]
        assert isinstance(exc, RuntimeError)
        assert str(exc) == "cannot reuse already awaited coroutine"

    print(callog)
    assert callog == ['setup',
                      'cancel', ('result', 500), ('switch', None, False),
                      ('switch', 100, False)]


def test_SwitchedCoroutine_exc_in_setup(callog, caplog):
    switcher = MockSwitcher(callog)
    exc = ValueError("sample exception")
    coro = async1func(switcher, callog,
                      lambda *args: callog.append('setup') or exc,
                      lambda *args: callog.append('cancel'),
                      catch_exception=True)

    with caplog.at_level(logging.ERROR):
        switcher.switch(coro, None)
        switcher.switch(coro, 100)
    assert len(caplog.records) == 1
    for record in caplog.records:
        exc = record.exc_info[1]
        assert isinstance(exc, RuntimeError)
        assert str(exc) == "cannot reuse already awaited coroutine"

    print(callog)
    assert callog == ['setup',
                      'cancel', ('catch', ValueError), ('result', None),
                      ('switch', None, False),
                      ('switch', 100, False)]


if __name__ == '__main__':
    pytest.main([__file__])
