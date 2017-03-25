import concurrent.futures
import os
import os.path
import tempfile
import time

import pytest
from squall.core import Dispatcher as API
from squall.core.abc import Future as AbcFuture

AbcFuture.register(concurrent.futures.Future)


@pytest.yield_fixture
def callog():
    _callog = list()
    yield _callog


@pytest.yield_fixture
def fifo_files():
    tempname = os.path.join(tempfile.mkdtemp(), 'A')
    os.mkfifo(tempname)
    rx_fifo = os.open(tempname, os.O_RDONLY | os.O_NONBLOCK)
    tx_fifo = os.open(tempname, os.O_WRONLY | os.O_NONBLOCK)
    yield rx_fifo, tx_fifo


def test_timing(callog):
    """ Checks timing of coroutines switching.
    """

    async def test01(api):
        while True:
            await api.sleep(0.1)
            callog.append(('test01', 'T', 1))

    async def test02(api):
        while True:
            await api.sleep(0.21)
            callog.append(('test02', 'T', 2))

    async def test05(api):
        await api.sleep(0.55)
        callog.append(('test05', 'T', 5))
        coro02.close()

    async def test07(api):
        await api.sleep(0.77)
        callog.append(('test07', 'T', 7))
        api.stop()

    api = API()
    coro01 = api.submit(test01)
    callog.append(('test01', 'C', 1))
    coro02 = api.submit(test02)
    callog.append(('test02', 'C', 2))
    coro05 = api.submit(test05)
    callog.append(('test05', 'C', 5))
    coro07 = api.submit(test07)
    callog.append(('test07', 'C', 7))
    api.start()

    print(callog)
    assert callog == [
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
    ]


def test_ready_io(callog, fifo_files):
    rx_fifo, tx_fifo = fifo_files

    async def corofuncTX(api, fifo):
        callog.append('<TX')
        try:
            await api.ready(fifo, api.WRITE)
            await api.sleep(0.11)
            os.write(fifo, b'AAA')
            await api.sleep(0.41)
            os.write(fifo, b'BBB')
            await api.sleep(0.11)
        finally:
            os.close(fifo)
            callog.append('TX>')

    async def corofuncRX(api, fifo):
        callog.append('<RX')
        try:
            while True:
                try:
                    await api.ready(fifo, api.READ, timeout=0.31)
                    data = os.read(fifo, 1024)
                    callog.append(data)
                    if data == b'BBB':
                        break
                except TimeoutError:
                    callog.append('TIMEOUT')
        finally:
            os.close(fifo)
            callog.append('RX>')

    async def corofunc(api):
        cnt = 0
        callog.append('<<')
        while cnt < 8:
            await api.sleep(0.1)
            callog.append('*')
            cnt += 1
            if cnt == 1:
                api.submit(corofuncTX, tx_fifo)
                api.submit(corofuncRX, rx_fifo)
        api.stop()
        callog.append('>>')

    api = API()
    api.submit(corofunc)
    api.start()

    print(callog)
    assert callog == [
        '<<', '*', '<TX', '<RX',
        '*', b'AAA',
        '*', '*', '*', 'TIMEOUT',
        '*', b'BBB', 'RX>',
        '*', 'TX>',
        '*', '>>']


@pytest.yield_fixture
def executor():
    _executor = concurrent.futures.ProcessPoolExecutor()
    yield _executor
    _executor.shutdown()


def func_sleep(seconds):
    time.sleep(seconds)
    return 'DONE!R', time.time()


def test_real_future(callog, executor):
    async def corofuncFT(api, executor, seconds):
        callog.append('<FT')
        try:
            future = executor.submit(func_sleep, seconds)
            result = await api.complete(future)
            callog.append(result[0])
        finally:
            callog.append('FT>')

    async def corofunc(api):
        cnt = 0
        callog.append('<<')
        while cnt < 5:
            await api.sleep(0.1)
            callog.append('*')
            cnt += 1
            if cnt == 1:
                api.submit(corofuncFT, executor, 0.35)
        api.stop()
        callog.append('>>')

    api = API()
    api.submit(corofunc)
    api.start()

    print(callog)
    assert callog == ['<<', '*', '<FT', '*', '*', '*', 'DONE!R', 'FT>', '*', '>>']


async def corofunc_sleep(api, seconds):
    await api.sleep(seconds)
    return 'DONE!A', time.time()


def test_async_future(callog):

    async def corofuncFT(api, seconds):
        callog.append('<FT')
        try:
            future = api.submit(corofunc_sleep, seconds)
            result = await api.complete(future)
            callog.append(result[0])
        finally:
            callog.append('FT>')

    async def corofunc(api):
        cnt = 0
        callog.append('<<')
        while cnt < 5:
            await api.sleep(0.1)
            callog.append('*')
            cnt += 1
            if cnt == 1:
                api.submit(corofuncFT, 0.35)
        api.stop()
        callog.append('>>')

    api = API()
    api.submit(corofunc)
    api.start()

    print(callog)
    assert callog == ['<<', '*', '<FT', '*', '*', '*', 'DONE!A', 'FT>', '*', '>>']


def test_both_future(callog, executor):

    async def corofuncFT(api):
        callog.append('<FT')
        try:
            future_a = api.submit(corofunc_sleep, 0.33)
            future_r = executor.submit(func_sleep, 0.35)
            result = await api.complete(future_a, future_r)
            callog.append(tuple(A[0] for A in sorted(result, key=lambda A: A[1])))
        finally:
            callog.append('FT>')

    async def corofunc(api):
        cnt = 0
        callog.append('<<')
        while cnt < 5:
            await api.sleep(0.1)
            callog.append('*')
            cnt += 1
            if cnt == 1:
                api.submit(corofuncFT)
        api.stop()
        callog.append('>>')

    api = API()
    api.submit(corofunc)
    api.start()

    print(callog)
    assert callog == ['<<', '*', '<FT', '*', '*', '*',  ('DONE!A', 'DONE!R'), 'FT>', '*', '>>']


if __name__ == '__main__':
    # pytest.main([__file__])
    pytest.main(['-k', 'test_timing'])


