import os
import time
import os.path
import tempfile

import _squall

dispatcher = _squall.Dispatcher()
CLEANUP = dispatcher.CLEANUP
TIMEOUT = dispatcher.TIMER
READ = dispatcher.READ
WRITE = dispatcher.WRITE


def test_watch_timer():

    calls = list()
    result = list()

    def callback01(revents, payload):
        result.append((0.1, revents))
        return True

    def callback15(revents, payload):
        result.append((0.151, revents))
        return True

    def callback02(revents, payload):
        result.append((0.21, revents))
        calls.append(True)
        if len(calls) == 1:
            dispatcher.release_watching(callback15)
            return True
        else:
            dispatcher.stop()

    dispatcher.watch_timer(callback01, 0.1)
    dispatcher.watch_timer(callback15, 0.151)
    dispatcher.watch_timer(callback02, 0.21)

    dispatcher.start()

    assert result == [(0.1, TIMEOUT), (0.151, TIMEOUT), (0.1, TIMEOUT),
                      (0.21, TIMEOUT), (0.1, TIMEOUT), (0.1, TIMEOUT),
                      (0.21, TIMEOUT), (0.1, CLEANUP)]


def test_exception():

    call = list()
    result = list()

    def callback01(revents, payload):
        result.append((0.1, revents))
        return True

    def callback15(revents, payload):
        result.append((0.15, revents))
        call.append(True)
        if len(call) == 2:
            raise RuntimeError("EXC")
        return True

    dispatcher.watch_timer(callback01, 0.1)
    dispatcher.watch_timer(callback15, 0.151)

    try:
        dispatcher.start()
    except RuntimeError as exc:
        result.append(str(exc))

    assert result == [(0.1, TIMEOUT), (0.15, TIMEOUT), (0.1, TIMEOUT),
                      (0.1, TIMEOUT), (0.15, TIMEOUT),
                      (0.1, CLEANUP), 'EXC']


def test_watch_io():

    call = list()
    result = list()
    tempname = os.path.join(tempfile.mkdtemp(), 'A')
    os.mkfifo(tempname)
    out_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
    in_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)

    def callback01(revents, payload):
        result.append((0.1, revents))
        return True

    def callback15(revents, payload):
        result.append((0.15, revents))
        call.append(True)
        if len(call) == 1:
            os.write(in_fifo, b'AAA')
        elif len(call) == 2:
            dispatcher.stop()
        return True

    def callbackIN(revents, payload):
        result.append(('IN', revents))

    def callbackOUT(revents, payload):
        result.append(('OUT', revents))
        if READ & revents:
            result.append(('OUT', os.read(out_fifo, 1024)))
        return True

    try:
        dispatcher.watch_timer(callback01, 0.1)
        dispatcher.watch_timer(callback15, 0.151)
        dispatcher.watch_io(callbackIN, in_fifo, WRITE)
        dispatcher.watch_io(callbackOUT, out_fifo, READ)

        dispatcher.start()
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


def test_multiwatchers():

    result = list()
    start_at = time.time()

    tempname = tempfile.mkdtemp()
    tempnameA = os.path.join(tempname, 'A')
    tempnameB = os.path.join(tempname, 'B')
    os.mkfifo(tempnameA)
    os.mkfifo(tempnameB)
    fifoA = os.open(tempnameA, os.O_RDWR | os.O_NONBLOCK)
    fifoB = os.open(tempnameB, os.O_RDWR | os.O_NONBLOCK)

    def callback(revents, payload):
        stamp = round(time.time() - start_at, 2)
        if revents == WRITE:
            stamp = (stamp, payload)
            dispatcher.watch_io(callback, payload, READ)
        elif revents == READ:
            stamp = (stamp, payload, os.read(fifoA, 1024))
        else:
            os.write(fifoA, b'A')
            dispatcher.watch_io(callback, fifoB, WRITE)
        result.append((stamp, revents))
        return True

    try:
        dispatcher.watch_timer(callback, 0.1)
        dispatcher.watch_timer(callback, 0.15)
        dispatcher.watch_io(callback, fifoA, WRITE)
        dispatcher.watch_timer(lambda *args: dispatcher.stop(), 0.31)
        dispatcher.start()
    finally:
        os.unlink(tempnameA)
        os.unlink(tempnameB)

    assert result == [
        ((0.0, fifoA), WRITE),
        (0.15, TIMEOUT), ((0.15, fifoB), WRITE), ((0.15, fifoA, b'A'), READ),
        (0.3, TIMEOUT), ((0.3, fifoB), WRITE), ((0.3, fifoA, b'A'), READ),
        (0.31, CLEANUP)]


if __name__ == '__main__':

    test_exception()
    test_watch_timer()
    test_watch_timer()
    test_watch_io()
    test_exception()
    test_watch_timer()
    test_exception()
    test_watch_io()
    test_multiwatchers()
