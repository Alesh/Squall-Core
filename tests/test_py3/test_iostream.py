import errno
import unittest

from squall import abc
from squall.coroutine import spawn, Dispatcher, IOStream
from squall.coroutine import READ, WRITE, TIMEOUT, ERROR


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


class MockAutoBuffer(abc.AutoBuffer):
    """
    """
    def __init__(self, callog, block_size=1024,  max_size=16 * 1024):
        self._block_size = (int(block_size / 64) * 64
                            if block_size > 256 else 256)
        self._max_size = (int(max_size / self.block_size) * self.block_size
                          if max_size > self.block_size * 8
                          else self.block_size * 8)
        self._closed = False
        self.callog = callog

    @property
    def closed(self):
        return self._closed

    @property
    def block_size(self):
        return self._block_size

    @property
    def max_size(self):
        return self._max_size

    @property
    def last_error(self):
        return None

    def watch_read_bytes(self, callback, number):
        self.callog.append(('watch_read_bytes', callback, number))
        return not self._closed

    def watch_read_until(self, callback, delimiter, max_number):
        self.callog.append(('watch_read_until', callback,
                            delimiter, max_number))
        return not self._closed

    def watch_flush(self, callback):
        self.callog.append(('watch_flush', callback))
        return not self._closed

    def write(self, data):
        self.callog.append(('write', data))
        return len(data)

    def cancel(self):
        self.callog.append(('buff:cancel',))

    def release(self):
        self._closed = True
        self.callog.append(('buff:release',))

abc.AutoBuffer.register(MockAutoBuffer)


class TestIOStream(unittest.TestCase):
    """ async/await with IOStream.
    """
    def __init__(self, *args, **kwargs):
        self.callog = list()
        self.disp = Dispatcher()
        self.disp._event_disp = MockEventDispatcher(self.callog)
        super(TestIOStream, self).__init__(*args, **kwargs)

    async def sample_corofunc(self, stream):
        awaitable = stream.read_bytes(4*1024)
        self.callog.append(('sample:awaitable', awaitable))
        return_value = await awaitable
        self.callog.append(('sample:return_value', return_value))
        try:
            return_value = await stream.read_until(b'\r\n',
                                                   64*1024, timeout=5.0)
            self.callog.append(('sample:return_value', return_value))
        except Exception as exc:
            self.callog.append(('sample:Exception', (exc
                                                     if type(exc) == 'type'
                                                     else type(exc))))
        if not stream.closed:
            stream.write(b'TEST')
        try:
            return_value = await stream.flush(timeout=7.0)
            self.callog.append(('sample:return_value', return_value))
        except Exception as exc:
            self.callog.append(('sample:Exception', (exc
                                                     if type(exc) == 'type'
                                                     else type(exc))))

    def test_switching_success(self):
        stream = IOStream(self.disp, MockAutoBuffer(self.callog, 260, 0))
        self.assertEqual(stream.block_size, 256)
        self.assertEqual(stream.buffer_size, 256*8)
        self.disp.spawn(self.sample_corofunc, stream)

        callback01 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_bytes'][-1]
        self.callog.append(('callback', READ, b'READ_BYTES'))
        callback01(READ, b'READ_BYTES')

        callback02 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_until'][-1]
        self.callog.append(('callback', READ, b'READ_UNTIL'))
        callback02(READ, b'READ_UNTIL')

        callback03 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_flush'][-1]
        self.callog.append(('callback', WRITE))
        callback03(WRITE)

        self.assertListEqual(self.callog, [
            ('sample:awaitable', callback01),
            ('watch_read_bytes', callback01, stream.buffer_size),
            ('callback', READ, b'READ_BYTES'),
            ('buff:cancel',),
            ('sample:return_value', b'READ_BYTES'),
            ('watch_timer', callback02, 5.0),
            ('watch_read_until', callback02, b'\r\n', stream.buffer_size),
            ('callback', READ, b'READ_UNTIL'),
            ('cancel', callback02),
            ('buff:cancel',),
            ('sample:return_value', b'READ_UNTIL'),
            ('write', b'TEST'),
            ('watch_timer', callback03, 7.0),
            ('watch_flush', callback03),
            ('callback', WRITE),
            ('cancel', callback03),
            ('buff:cancel',),
            ('sample:return_value', WRITE)])

        self.assertFalse(stream.closed)

    def test_close(self):
        stream = IOStream(self.disp, MockAutoBuffer(self.callog, 1000, 50000))
        self.assertEqual(stream.block_size, 960)
        self.assertEqual(stream.buffer_size, 49920)
        coro = self.disp.spawn(self.sample_corofunc, stream)

        callback01 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_bytes'][-1]
        self.callog.append(('callback', READ, b'READ_BYTES'))
        callback01(READ, b'READ_BYTES')

        callback02 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_until'][-1]

        coro.close()
        stream.abort()

        self.assertListEqual(self.callog, [
            ('sample:awaitable', callback01),
            ('watch_read_bytes', callback01, 4*1024),
            ('callback', READ, b'READ_BYTES'),
            ('buff:cancel',),
            ('sample:return_value', b'READ_BYTES'),
            ('watch_timer', callback02, 5.0),
            ('watch_read_until', callback02, b'\r\n', 49920),
            ('cancel', callback02),
            ('buff:cancel',),
            ('buff:release',)])

        self.assertTrue(stream.closed)

    def test_closed(self):
        stream = IOStream(self.disp, MockAutoBuffer(self.callog, 1000, 50000))
        self.assertEqual(stream.block_size, 960)
        self.assertEqual(stream.buffer_size, 49920)
        self.disp.spawn(self.sample_corofunc, stream)

        callback01 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_bytes'][-1]
        stream.abort()
        self.callog.append(('callback', READ, b'READ_BYTES'))
        callback01(READ, b'READ_BYTES')

        self.assertListEqual(self.callog, [
            ('sample:awaitable', callback01),
            ('watch_read_bytes', callback01, 4096),
            ('buff:release',),
            ('callback', READ, b'READ_BYTES'),
            ('buff:cancel',),
            ('sample:return_value', b'READ_BYTES'),
            ('sample:Exception', ConnectionError),
            ('sample:Exception', ConnectionError)])


    def test_error_andttimeout(self):
        stream = IOStream(self.disp, MockAutoBuffer(self.callog, 2000, 0))
        self.assertEqual(stream.block_size, 1984)
        self.assertEqual(stream.buffer_size, 1984*8)
        self.disp.spawn(self.sample_corofunc, stream)

        callback01 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_bytes'][-1]
        self.callog.append(('callback', READ, b'READ_BYTES'))
        callback01(READ, b'READ_BYTES')

        callback02 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_read_until'][-1]
        self.callog.append(('callback', TIMEOUT))
        callback02(TIMEOUT)

        callback03 = [b[0]
                      for a, *b in self.callog
                      if a == 'watch_flush'][-1]
        self.callog.append(('callback', ERROR, errno.ECONNRESET))
        callback03(ERROR, errno.ECONNRESET)

        self.assertListEqual(self.callog, [
            ('sample:awaitable', callback01),
            ('watch_read_bytes', callback01, 4*1024),
            ('callback', READ, b'READ_BYTES'),
            ('buff:cancel',),
            ('sample:return_value', b'READ_BYTES'),
            ('watch_timer', callback02, 5.0),
            ('watch_read_until', callback02, b'\r\n', stream.buffer_size),
            ('callback', TIMEOUT),
            ('cancel', callback02),
            ('buff:cancel',),
            ('sample:Exception', TimeoutError),
            ('write', b'TEST'),
            ('watch_timer', callback03, 7.0),
            ('watch_flush', callback03),
            ('callback', ERROR, errno.ECONNRESET),
            ('cancel', callback03),
            ('buff:cancel',),
            ('sample:Exception', ConnectionResetError)])


if __name__ == '__main__':
    unittest.main()
