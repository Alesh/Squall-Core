import pytest
import logging
from functools import partial
from squall.core import Dispatcher, TCPServer, TCPClient
from squall.core.utils import timeout_gen


@pytest.yield_fixture
def callog():
    _callog = list()
    yield _callog


class EchoServer(TCPServer):

    def __init__(self, before_start):
        self._before_start = before_start
        super().__init__(self.echo_handler)

    async def echo_handler(self, disp, stream, addr):
        try:
            while stream.active:
                data = await stream.read_exactly(1)
                if data:
                    data += stream.read(stream.buffer_size)
                    stream.write(data)
        except: pass
        finally:
            stream.close()

    def before_start(self, disp):
        disp.submit(self._before_start)


def test_client_server(callog):

    async def stream_handler(timeout, disp, stream, address):
        result = []
        timeout = timeout_gen(timeout)
        try:
            stream.write(b'0123456789ABCDEF\r\n')
            data = await stream.read_exactly(10, timeout=next(timeout))
            result.append(data)
            data = await stream.read_until(b'\r\n', timeout=next(timeout))
            result.append(data)
            data = await stream.read_until(b'\r\n', timeout=next(timeout))
            result.append(data)
        except Exception as exc:
            result.append(type(exc))
        finally:
            stream.close()
        return result

    async def client_request(disp, N):
        try:
            client = TCPClient(disp)
            timeout = float(N + 1) / 10.0
            result = await client.connect(partial(stream_handler, timeout),
                                          ('127.0.0.1', 22077), timeout=timeout)
        except Exception as exc:
            result = exc
        return result

    async def start_requests(disp):
        requests = list()
        for N in range(12):
            requests.append(disp.submit(client_request, N))
        await disp.complete(*requests, timeout=1.05)
        result = [(request.exception() or request.result()
                   if not request.cancelled() else 'CANCELLED') for request in requests]
        callog.extend(result)
        disp.stop()

    server = EchoServer(start_requests)
    server.bind(22077, 'localhost')
    server.start()

    print(callog)
    assert callog == [
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        [b'0123456789', b'ABCDEF\r\n', TimeoutError],
        'CANCELLED',
        'CANCELLED'
    ]


if __name__ == '__main__':
    pytest.main([__file__])
