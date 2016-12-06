import unittest
from squall import abc
from testfixtures import LogCapture
from squall.coroutine import Dispatcher, spawn, sleep, ready
from squall.coroutine import TIMEOUT, ERROR, READ


class MockEventDispatcher(object):
    """
    """
    def __init__(self, callog):
        self.callog = callog

    def watch_timer(self, callback, seconds, once=False):
        self.callog.append(('watch_timer', callback, seconds))
        return True

    def watch_io(self, callback, fd, events, once=False):
        self.callog.append(('watch_io', callback, fd, events))
        return True

    def cancel(self, callback):
        self.callog.append(('cancel', callback))

abc.EventDispatcher.register(MockEventDispatcher)


class TestCoroutineSwitching(unittest.TestCase):
    """ Event-driven coroutine switching.
    """

    def __init__(self, *args, **kwargs):
        self.callog = list()
        self.disp = Dispatcher()
        self.disp._event_disp = MockEventDispatcher(self.callog)
        super().__init__(*args, **kwargs)

    def setUp(self):
        self.callog.clear()

    async def sample_corofunc(self):
        awaitable = sleep(2.5)
        self.callog.append(('sample:awaitable', awaitable))
        return_value = await awaitable
        self.callog.append(('sample:return_value', return_value))
        try:
            return_value = await sleep(5.0)
            self.callog.append(('sample:return_value', return_value))
        except Exception as exc:
            self.callog.append(('sample:Exception',
                               (exc if type(exc) == 'type' else type(exc))))
        return_value = await sleep(7.0)
        self.callog.append(('sample:return_value', return_value))

    def test_coroutine_switch_success(self):
        """ Successed coroutine switching.
        """
        self.disp.spawn(self.sample_corofunc)

        callback01 = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        self.callog.append(('callback', TIMEOUT))
        self.assertFalse(callback01(TIMEOUT))

        callback02 = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        self.callog.append(('callback', TIMEOUT))
        self.assertFalse(callback02(TIMEOUT))

        callback03 = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        self.callog.append(('callback', TIMEOUT))
        self.assertFalse(callback03(TIMEOUT))

        self.assertEqual(self.callog, [
            ('sample:awaitable', callback01),
            ('watch_timer', callback01, 2.5),
            ('callback', TIMEOUT),
            ('cancel', callback01),
            ('sample:return_value', TIMEOUT),
            ('watch_timer', callback02, 5.0),
            ('callback', TIMEOUT),
            ('cancel', callback02),
            ('sample:return_value', TIMEOUT),
            ('watch_timer', callback03, 7.0),
            ('callback', TIMEOUT),
            ('cancel', callback03),
            ('sample:return_value', TIMEOUT)
        ])

    def test_coroutine_close(self):
        """ A coroutine closes while suspended running.
        """
        coro = self.disp.spawn(self.sample_corofunc)

        callback = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        coro.close()

        self.assertEqual(self.callog, [
            ('sample:awaitable', callback),
            ('watch_timer', callback, 2.5),
            ('cancel', callback)])

    def test_coroutine_switch_catched_error(self):
        """ Catches exception while a coroutine is running.
        """
        self.disp.spawn(self.sample_corofunc)

        callback01 = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        self.callog.append(('callback', TIMEOUT))
        callback01(TIMEOUT)

        callback02 = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        self.callog.append(('callback', ERROR))
        callback02(ERROR)

        callback03 = [b[0] for a, *b in self.callog if a == 'watch_timer'][-1]
        self.callog.append(('callback', TIMEOUT))
        callback03(TIMEOUT)

        self.assertEqual(self.callog, [
            ('sample:awaitable', callback01),

            ('watch_timer', callback01, 2.5),
            ('callback', TIMEOUT),
            ('cancel', callback01),
            ('sample:return_value', TIMEOUT),

            ('watch_timer', callback02, 5.0),
            ('callback', ERROR),
            ('cancel', callback02),
            ('sample:Exception', OSError),

            ('watch_timer', callback03, 7.0),
            ('callback', TIMEOUT),
            ('cancel', callback03),
            ('sample:return_value', TIMEOUT)
        ])

    def test_coroutine_switch_uncatched_error(self):
        """ Uncatched error while switching.
        """
        with LogCapture() as lc:
            coro = self.disp.spawn(self.sample_corofunc)

            callback01 = [b[0]
                          for a, *b in self.callog
                          if a == 'watch_timer'][-1]
            self.callog.append(('callback', ERROR))
            callback01(ERROR)

            callback02 = [b[0]
                          for a, *b in self.callog
                          if a == 'watch_timer'][-1]
            self.callog.append(('callback', TIMEOUT))
            callback02(TIMEOUT)

            callback03 = [b[0]
                          for a, *b in self.callog
                          if a == 'watch_timer'][-1]
            self.callog.append(('callback', TIMEOUT))
            callback03(TIMEOUT)

        self.assertEqual(self.callog, [
            ('sample:awaitable', callback01),
            ('watch_timer', callback01, 2.5),
            ('callback', ERROR),
            ('cancel', callback01),
            ('callback', TIMEOUT),
            ('cancel', callback02),
            ('callback', TIMEOUT),
            ('cancel', callback03),
        ])

        lc.check(
            ('squall.coroutine', 'ERROR',
             "Coroutine {} closed due to uncaught exception".format(coro)),
            ('squall.coroutine', 'ERROR',
             "Coroutine {} closed due to uncaught exception".format(coro)),
            ('squall.coroutine', 'ERROR',
             "Coroutine {} closed due to uncaught exception".format(coro)),
        )

    async def sample_corofunc2(self):
        awaitable = ready(2, READ)
        self.callog.append(('sample:awaitable', awaitable))
        return_value = await awaitable
        self.callog.append(('sample:return_value', return_value))

        try:
            return_value = await ready(5, READ)
            self.callog.append(('sample:return_value', return_value))
        except Exception as exc:
            self.callog.append(('sample:Exception', (exc
                                                     if type(exc) == 'type'
                                                     else type(exc))))
        try:
            return_value = await ready(7, READ, timeout=7.0)
            self.callog.append(('sample:return_value', return_value))
        except Exception as exc:
            self.callog.append(('sample:Exception', (exc
                                                     if type(exc) == 'type'
                                                     else type(exc))))

    def test_coroutine_switch_with_timeout(self):
        """ A coroutine switches back by timeout.
        """
        self.disp.spawn(self.sample_corofunc2)

        callback01 = [b[0] for a, *b in self.callog if a == 'watch_io'][-1]
        self.callog.append(('callback', READ))
        callback01(READ)

        callback02 = [b[0] for a, *b in self.callog if a == 'watch_io'][-1]
        self.callog.append(('callback', ERROR))
        callback02(ERROR)

        callback03 = [b[0] for a, *b in self.callog if a == 'watch_io'][-1]
        self.callog.append(('callback', TIMEOUT))
        callback03(TIMEOUT)

        self.assertEqual(self.callog, [
            ('sample:awaitable', callback01),

            ('watch_io', callback01, 2, READ),
            ('callback', READ),
            ('cancel', callback01),
            ('sample:return_value', READ),

            ('watch_io', callback02, 5, READ),
            ('callback', ERROR),
            ('cancel', callback02),
            ('sample:Exception', OSError),

            ('watch_timer', callback03, 7.0),
            ('watch_io', callback03, 7, READ),
            ('callback', TIMEOUT),
            ('cancel', callback03),
            ('sample:Exception', TimeoutError),
        ])


if __name__ == '__main__':
    unittest.main()
