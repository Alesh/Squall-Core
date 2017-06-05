import time
import os.path
import tempfile
import pytest
from squall.core import Dispatcher, FileStream


@pytest.yield_fixture
def callog():
    _callog = list()
    yield _callog


def test_IOStream(callog):
    """ IOStream unittest """

    async def cororeader(disp, stream):
        callog.append(('R', 0))

        await disp.sleep(0.05)
        data = await stream.read_until(b'\n')
        callog.append(('R', 1, data))

        data = await stream.read_until(b'\r\n')
        callog.append(('R', 2, data))

        try:
            data = await stream.read_until(b'\t\t', max_bytes=10)
            callog.append(('R', 3, data))
        except Exception as exc:
            callog.append(('R', 3, type(exc)))

        data = await stream.read_exactly(8)
        callog.append(('R', 4, data, stream.incoming_size))

        data = await stream.read_exactly(8)
        callog.append(('R', 5, data))

        data = stream.read(100)
        callog.append(('R', 6, data))

        await disp.sleep(0.2)
        data = stream.read(100)
        callog.append(('R', 7, len(data)))

        data = b''
        while True:
            try:
                data += await stream.read_exactly(1024)
            except Exception as exc:
                callog.append(('R', 8, type(exc)))
                break

        callog.append(('R', 9, len(data)))

        data = stream.read(stream.buffer_size)
        callog.append(('R', 10, len(data)))

        read_stm.close()
        callog.append(('R', 'END'))

    async def corowriter(disp, stream):
        callog.append(('W', 0))

        sent = stream.write(b'AAA\nBBB')
        result = await stream.flush()
        callog.append(('W', 1, sent, result))

        await disp.sleep(0.05)
        sent = stream.write(b'\r\n0123456789')
        result = await stream.flush()
        callog.append(('W', 2, sent, result))

        await disp.sleep(0.5)

        await disp.sleep(0.05)
        sent = stream.write(b'ABCDEFXXX')
        result = await stream.flush()
        callog.append(('W', 3, sent, result))

        await disp.sleep(0.1)
        sent = stream.write(b'A' * (96 * 1024))
        callog.append(('W', 4, sent, (96 * 1024)))
        result = await stream.flush()
        callog.append(('W', 5, result))

        write_stm.close()
        callog.append(('W', 'END'))

    async def terminator(disp):
        await disp.sleep(1.0)
        callog.append(('STOP'))
        disp.stop()

    disp = Dispatcher()
    tempname = os.path.join(tempfile.mkdtemp(), 'A2')
    os.mkfifo(tempname)
    read_stm = FileStream(disp, tempname, os.O_RDONLY)
    write_stm = FileStream(disp, tempname, os.O_WRONLY,
                           block_size=16000, buffer_size=90000)

    assert read_stm.block_size == 1024
    assert read_stm.buffer_size == 1024 * 4
    assert read_stm.active
    assert disp.submit(cororeader, read_stm)

    assert write_stm.block_size == 1024 * 16
    assert write_stm.buffer_size == 1024 * 16 * 5
    assert write_stm.active
    assert disp.submit(corowriter, write_stm)

    disp.submit(terminator)
    disp.start()

    print(callog)
    assert callog == [
        ('R', 0),
        ('W', 0),
        ('W', 1, 7, True),
        ('R', 1, b'AAA\n'),
        ('W', 2, 12, True),
        ('R', 2, b'BBB\r\n'),
        ('R', 3, LookupError),
        ('R', 4, b'01234567', 2),
        ('W', 3, 9, True),
        ('R', 5, b'89ABCDEF'),
        ('R', 6, b'XXX'),
        ('W', 4, 81920, 98304),
        ('R', 7, 100),
        ('W', 5, True),
        ('W', 'END'),
        ('R', 8, EOFError),
        ('R', 9, 80896),
        ('R', 10, 924),
        ('R', 'END'),
    'STOP']

if __name__ == '__main__':
    pytest.main([__file__])
