import os
import os.path
import tempfile
import unittest
from squall import abc
from collections import deque
from squall.coroutine import EventDispatcher


class TestEventDispatcher(unittest.TestCase):
    """ Event dispatcher
    """

    def __init__(self, *args, **kwargs):
        self.callog = list()
        super(TestEventDispatcher, self).__init__(*args, **kwargs)

    def setUp(self):
        self.callog.clear()

    def test_timing(self):
        event_disp = EventDispatcher()
        self.assertTrue(isinstance(event_disp, abc.EventDispatcher))

        def callback01(revents):
            self.callog.append(('callback01', revents))
            return True

        def callback02(revents):
            self.callog.append(('callback02', revents))
            return True

        def callback03(revents):
            self.callog.append(('callback03', revents))
            return True

        def callback05(revents):
            self.callog.append(('callback05', revents))
            event_disp.cancel(callback02)
            return False

        def callback07(revents):
            self.callog.append(('callback07', revents))
            event_disp.stop()
            return False

        self.assertTrue(event_disp.watch_timer(callback01, 0.1))
        self.assertTrue(event_disp.watch_timer(callback02, 0.05))
        self.assertTrue(event_disp.watch_timer(callback02, 0.21))
        self.assertTrue(event_disp.watch_timer(callback03, 0.31, True))
        self.assertTrue(event_disp.watch_timer(callback05, 0.55))
        self.assertTrue(event_disp.watch_timer(callback07, 0.77))
        event_disp.start()

        self.assertListEqual(self.callog, [
            ('callback01', event_disp.TIMEOUT),
            ('callback01', event_disp.TIMEOUT),
            ('callback02', event_disp.TIMEOUT),
            ('callback01', event_disp.TIMEOUT),
            ('callback03', event_disp.TIMEOUT),
            ('callback01', event_disp.TIMEOUT),
            ('callback02', event_disp.TIMEOUT),
            ('callback01', event_disp.TIMEOUT),
            ('callback05', event_disp.TIMEOUT),
            ('callback01', event_disp.TIMEOUT),
            ('callback01', event_disp.TIMEOUT),
            ('callback07', event_disp.TIMEOUT),
            ('callback01', event_disp.CLEANUP),
        ])

    def test_ready_io(self):
        event_disp = EventDispatcher()
        tempname = os.path.join(tempfile.mkdtemp(), 'A')
        os.mkfifo(tempname)

        rx_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
        tx_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)

        parts = deque([b'BOF', b'BODY', b'EOF'])

        def callbackTX(revents):
            self.callog.append(('callbackTX', revents))
            if revents == event_disp.WRITE:
                data = parts.popleft()
                os.write(tx_fifo, data)
                self.callog.append(('os.write', data))
                if data == b'EOF':
                    event_disp.cancel(callbackTX)
                return False
            if revents == event_disp.TIMEOUT:
                self.assertTrue(event_disp.watch_io(callbackTX, tx_fifo,
                                                    event_disp.WRITE))
                return True

        def callbackRX(revents):
            self.callog.append(('callbackRX', revents))
            if revents == event_disp.READ:
                data = os.read(rx_fifo, 1024)
                self.callog.append(('os.read', data))
                if data == b'EOF':
                    event_disp.stop()
                return True
            elif revents == event_disp.CLEANUP:
                os.close(tx_fifo)
                os.close(rx_fifo)

        self.assertTrue(event_disp.watch_io(callbackRX, rx_fifo,
                                            event_disp.READ))
        self.assertTrue(event_disp.watch_timer(callbackTX, 0.1))
        event_disp.start()

        self.assertListEqual(self.callog, [
            ('callbackTX', event_disp.TIMEOUT),
            ('callbackTX', event_disp.WRITE),
            ('os.write', b'BOF'),
            ('callbackRX', event_disp.READ),
            ('os.read', b'BOF'),
            ('callbackTX', event_disp.TIMEOUT),
            ('callbackTX', event_disp.WRITE),
            ('os.write', b'BODY'),
            ('callbackRX', event_disp.READ),
            ('os.read', b'BODY'),
            ('callbackTX', event_disp.TIMEOUT),
            ('callbackTX', event_disp.WRITE),
            ('os.write', b'EOF'),
            ('callbackRX', event_disp.READ),
            ('os.read', b'EOF'),
            ('callbackRX', event_disp.CLEANUP)
        ])


if __name__ == '__main__':
    unittest.main()
