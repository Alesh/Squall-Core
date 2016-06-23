import os
import os.path
import tempfile

try:
    from squall._squall import start, stop, setup_wait
    from squall._squall import CLEANUP, TIMEOUT, READ, WRITE
    from squall._squall import setup_wait_io, release_watching
except ImportError:
    from squall._tornado import start, stop, setup_wait
    from squall._tornado import CLEANUP, TIMEOUT, READ, WRITE
    from squall._tornado import setup_wait_io, release_watching


def test_setup_wait():

    calls = list()
    result = list()

    def callback01(revents):
        result.append((0.1, revents))
        return True

    def callback15(revents):
        result.append((0.151, revents))
        return True

    def callback02(revents):
        result.append((0.21, revents))
        calls.append(True)
        if len(calls) == 1:
            release_watching(callback15)
            return True
        else:
            stop()

    setup_wait(callback01, 0.1)
    setup_wait(callback15, 0.151)
    setup_wait(callback02, 0.21)

    start()

    assert result == [(0.1, TIMEOUT), (0.151, TIMEOUT), (0.1, TIMEOUT),
                      (0.21, TIMEOUT), (0.1, TIMEOUT), (0.1, TIMEOUT),
                      (0.21, TIMEOUT), (0.1, CLEANUP)]


def test_exception():

    call = list()
    result = list()

    def callback01(revents):
        result.append((0.1, revents))
        return True

    def callback15(revents):
        result.append((0.15, revents))
        call.append(True)
        if len(call) == 2:
            raise RuntimeError("EXC")
        return True

    setup_wait(callback01, 0.1)
    setup_wait(callback15, 0.151)

    try:
        start()
    except RuntimeError as exc:
        result.append(str(exc))

    assert result == [(0.1, TIMEOUT), (0.15, TIMEOUT), (0.1, TIMEOUT),
                      (0.1, TIMEOUT), (0.15, TIMEOUT),
                      (0.1, CLEANUP), 'EXC']


def test_setup_wait_io():

    call = list()
    result = list()
    tempname = os.path.join(tempfile.mkdtemp(), 'A')
    os.mkfifo(tempname)
    out_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
    in_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)

    def callback01(revents):
        result.append((0.1, revents))
        return True

    def callback15(revents):
        result.append((0.15, revents))
        call.append(True)
        if len(call) == 1:
            os.write(in_fifo, b'AAA')
        elif len(call) == 2:
            stop()
        return True

    def callbackIN(revents):
        result.append(('IN', revents))

    def callbackOUT(revents):
        result.append(('OUT', revents))
        if READ & revents:
            result.append(('OUT', os.read(out_fifo, 1024)))
        return True

    try:
        setup_wait(callback01, 0.1)
        setup_wait(callback15, 0.151)
        setup_wait_io(callbackIN, in_fifo, WRITE)
        setup_wait_io(callbackOUT, out_fifo, READ)

        start()
    finally:
        os.close(in_fifo)
        os.close(out_fifo)
        os.unlink(tempname)
        os.rmdir(os.path.dirname(tempname))

    assert result.index((0.1, CLEANUP)) >= 8
    assert result.index((0.15, CLEANUP)) >= 8
    assert result.index(('OUT', CLEANUP)) >= 8
    result.remove((0.1, CLEANUP))
    result.remove((0.15, CLEANUP))
    result.remove(('OUT', CLEANUP))

    assert result == [('IN', WRITE), (0.1, TIMEOUT), (0.15, TIMEOUT),
                      ('OUT', READ), ('OUT', b'AAA'), (0.1, TIMEOUT),
                      (0.1, TIMEOUT), (0.15, TIMEOUT)]

if __name__ == '__main__':

    test_setup_wait()
    test_setup_wait_io()
    test_exception()
    test_setup_wait()
    test_exception()
    test_setup_wait_io()
