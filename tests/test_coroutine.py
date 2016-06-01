import os
import os.path
import tempfile
from squall.coroutine import start, stop, spawn, sleep, ready, READ, WRITE


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


if __name__ == '__main__':

    test_ready_and_close()
