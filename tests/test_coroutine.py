import os
import os.path
import tempfile
from time import time
from squall.coroutine import start, stop, spawn
from squall.coroutine import sleep, ready, _SwitchBack
from squall.dispatcher import setup_wait, CLEANUP, ERROR, READ, WRITE


def test_sleep():

    result = list()

    async def corofunc():
        start_at = time()
        await sleep(0.1)
        result.append(round(time() - start_at, 1))
        await sleep(0.5)
        result.append(round(time() - start_at, 1))
        await sleep(0.2)
        result.append(round(time() - start_at, 1))

    spawn(corofunc)
    start()

    assert result == [0.1, 0.6, 0.8]


def close_awited():

    result = list()

    async def corofuncA():
        result.append('>>A')
        await sleep(0.1)
        result.append('A01')
        await sleep(10.0)
        result.append('<<A')

    async def corofuncB():
        try:
            result.append('>>B')
            await sleep(0.1)
            result.append('B01')
            await sleep(10.0)
            result.append('<<B')
        except GeneratorExit:
            result.append('**B')

    async def corofuncC(ca, cb):
        result.append('>>C')
        await sleep(0.1)
        result.append('C01')
        await sleep(0.2)
        result.append('C02')
        ca.close()
        cb.close()
        result.append('<<C')

    ca = spawn(corofuncA)
    cb = spawn(corofuncB)
    spawn(corofuncC, ca, cb)
    start()

    assert result == ['>>A', '>>B', '>>C', 'A01', 'B01', 'C01',
                      'C02', '**B', '<<C']


def test__SwitchBack_ERROR_CLEANUP():

    result = list()
    switch_back = [None]

    def test():
        def setup_test(ctx):
            switch_back[0] = ctx
        return _SwitchBack(setup_test)

    async def corofunc01():
        result.append('<<')
        try:
            while True:
                await sleep(0.1)
                result.append('*')
        except GeneratorExit:
            result.append('>>')

    async def corofuncSW(mark):
        try:
            result.append('<<' + mark)
            while True:
                try:
                    rv = await test()
                    result.append(rv)
                except OSError:
                    result.append('ERR')
        except GeneratorExit:
            result.append(mark + '>>')

    spawn(corofunc01)
    spawn(corofuncSW, 'A')
    setup_wait(lambda event: switch_back[0](event), 0.11)
    setup_wait(lambda event: switch_back[0](ERROR), 0.21)
    setup_wait(lambda event: switch_back[0](event), 0.31)
    setup_wait(lambda event: switch_back[0](CLEANUP), 0.51)
    setup_wait(lambda event: stop(), 0.61)
    start()

    assert result == ['<<', '<<A', '*', 256, '*', 'ERR',
                      '*', 256, '*', '*', 'A>>', '*', '>>']


def test_ready_and_close():
    result = list()
    tempname = os.path.join(tempfile.mkdtemp(), 'A')
    os.mkfifo(tempname)

    rx_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
    tx_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)

    async def corofuncTX(fifo):
        result.append('<TX')
        try:
            await ready(fifo, WRITE)
            await sleep(0.11)
            os.write(fifo, b'AAA')
            await sleep(0.41)
            os.write(fifo, b'BBB')
            await sleep(0.11)
        finally:
            os.close(fifo)
            result.append('TX>')

    async def corofuncRX(fifo):
        result.append('<RX')
        try:
            while True:
                try:
                    await ready(fifo, READ, timeout=0.31)
                    data = os.read(fifo, 1024)
                    result.append(data)
                    if data == b'BBB':
                        break
                except TimeoutError:
                    result.append('TIMEOUT')
        finally:
            os.close(fifo)
            result.append('RX>')

    async def corofunc():
        cnt = 0
        result.append('<<')
        while cnt < 8:
            await sleep(0.1)
            result.append('*')
            cnt += 1
            if cnt == 1:
                spawn(corofuncTX, tx_fifo)
                spawn(corofuncRX, rx_fifo)
        stop()
        result.append('>>')

    spawn(corofunc)
    start()

    assert result == ['<<', '*', '<TX', '<RX', '*', b'AAA', '*',
                      '*', '*', 'TIMEOUT', '*', b'BBB', 'RX>',
                      '*', 'TX>', '*', '>>']


def test_ready_and_close2():
    result = list()
    tempname = os.path.join(tempfile.mkdtemp(), 'A')
    os.mkfifo(tempname)

    rx_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
    tx_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)

    async def corofuncTX(fifo):
        result.append('<TX')
        try:
            await ready(fifo, WRITE)
            await sleep(0.1)
            os.write(fifo, b'AAA')
            await sleep(0.41)
            os.write(fifo, b'BBB')
            await sleep(1.0)
        finally:
            os.close(fifo)
            result.append('TX>')

    async def corofuncRX(fifo):
        result.append('<RX')
        try:
            while True:
                try:
                    await ready(fifo, READ, timeout=0.3)
                    data = os.read(fifo, 1024)
                    result.append(data)
                    if data == b'BBB':
                        break
                except TimeoutError:
                    result.append('TIMEOUT')
        finally:
            os.close(fifo)
            result.append('RX>')

    async def corofunc():
        cnt = 0
        result.append('<<')
        tx_coro = rx_coro = None
        while cnt < 7:
            await sleep(0.1)
            result.append('*')
            cnt += 1
            if cnt == 1:
                tx_coro = spawn(corofuncTX, tx_fifo)
                rx_coro = spawn(corofuncRX, rx_fifo)
        result.append('>>')
        tx_coro.close()
        rx_coro.close()

    spawn(corofunc)
    start()

    assert result == ['<<', '*', '<TX', '<RX', '*', b'AAA', '*',
                      '*', 'TIMEOUT', '*', '*', b'BBB', 'RX>',
                      '*', '>>', 'TX>']


if __name__ == '__main__':

    test_sleep()
    close_awited()
    test__SwitchBack_ERROR_CLEANUP()
    test_ready_and_close()
    test_ready_and_close2()
