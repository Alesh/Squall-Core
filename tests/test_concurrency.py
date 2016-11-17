import os
import os.path
import tempfile
import unittest

from squall.coroutine import Dispatcher
from squall.coroutine import current, spawn, start, stop
from squall.coroutine import sleep, ready, READ, WRITE


class TestConcurrency(unittest.TestCase):
    """ Several coroutines are concurrent running.
    """
    def __init__(self, *args, **kwargs):
        self.callog = list()
        super(TestConcurrency, self).__init__(*args, **kwargs)

    def setUp(self):
        self.callog.clear()

    def tearDown(self):
        delattr(Dispatcher._tls, 'instance')

    def test_timing(self):
        """ Checks timing of coroutines switching.
        """

        async def test01():
            while True:
                await sleep(0.1)
                self.callog.append((current().__name__, 'T', 1))
        coro01 = spawn(test01)
        self.callog.append((coro01.__name__, 'C', 1))

        async def test02():
            while True:
                await sleep(0.21)
                self.callog.append((current().__name__, 'T', 2))
        coro02 = spawn(test02)
        self.callog.append((coro02.__name__, 'C', 2))

        async def test05():
            await sleep(0.55)
            self.callog.append((current().__name__, 'T', 5))
            coro02.close()
        coro05 = spawn(test05)
        self.callog.append((coro05.__name__, 'C', 5))

        async def test07():
            await sleep(0.77)
            self.callog.append((current().__name__, 'T', 7))
            stop()
        coro07 = spawn(test07)
        self.callog.append((coro07.__name__, 'C', 7))

        start()

        self.assertEqual(self.callog, [
            ('test01', 'C', 1),
            ('test02', 'C', 2),
            ('test05', 'C', 5),
            ('test07', 'C', 7),

            ('test01', 'T', 1),

            ('test01', 'T', 1),
            ('test02', 'T', 2),

            ('test01', 'T', 1),

            ('test01', 'T', 1),
            ('test02', 'T', 2),

            ('test01', 'T', 1),
            ('test05', 'T', 5),

            ('test01', 'T', 1),

            ('test01', 'T', 1),
            ('test07', 'T', 7)
        ])

    def test_ready_io(self):
        tempname = os.path.join(tempfile.mkdtemp(), 'A')
        os.mkfifo(tempname)

        rx_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
        tx_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)

        async def corofuncTX(fifo):
            self.callog.append('<TX')
            try:
                await ready(fifo, WRITE)
                await sleep(0.11)
                os.write(fifo, b'AAA')
                await sleep(0.41)
                os.write(fifo, b'BBB')
                await sleep(0.11)
            finally:
                os.close(fifo)
                self.callog.append('TX>')

        async def corofuncRX(fifo):
            self.callog.append('<RX')
            try:
                while True:
                    try:
                        await ready(fifo, READ, timeout=0.31)
                        data = os.read(fifo, 1024)
                        self.callog.append(data)
                        if data == b'BBB':
                            break
                    except TimeoutError:
                        self.callog.append('TIMEOUT')
            finally:
                os.close(fifo)
                self.callog.append('RX>')

        async def corofunc():
            cnt = 0
            self.callog.append('<<')
            while cnt < 8:
                await sleep(0.1)
                self.callog.append('*')
                cnt += 1
                if cnt == 1:
                    spawn(corofuncTX, tx_fifo)
                    spawn(corofuncRX, rx_fifo)
            stop()
            self.callog.append('>>')

        spawn(corofunc)
        start()

        self.assertEqual(self.callog, [
            '<<', '*', '<TX', '<RX',
            '*', b'AAA',
            '*', '*', '*', 'TIMEOUT',
            '*', b'BBB', 'RX>',
            '*', 'TX>',
            '*', '>>'])


if __name__ == '__main__':
    unittest.main()
