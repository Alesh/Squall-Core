import pytest
from time import time
from squall.core import Dispatcher, TCPClient, TCPServer
from squall.core.utils import timeout_gen


@pytest.yield_fixture
def callog():
    _callog = list()
    yield _callog


class EchoTestServer(TCPServer):

    def __init__(self, callog, timeout):
        self.callog = callog
        self.timeout = timeout
        super().__init__(self.echo_handler)

    async def echo_handler(self, api, stream, address):
        tg = timeout_gen(self.timeout)
        if stream.active:
            try:
                data = await stream.read_until(b'>>>', timeout=next(tg))
                print('!! data', data)
                if data != b'>>>':
                    return
                data = await stream.read_exactly(3, timeout=next(tg))
                if data != b'XXX':
                    return
                data = await stream.read_until(b'\r\n', timeout=next(tg))
                parts = data.split(b'!')
                sleep_timeout = float(parts[1]) / 1000
                await api.sleep(sleep_timeout)
                stream.write(str(int(time() * 1000)).encode() + b'!' + data)
                await stream.flush(timeout=next(tg))
            except Exception as exc:
                self.callog.append(('server_exc', exc))
            finally:
                stream.close()

    async def client_request(self, api, number):

        async def client_handler(api, stream, address):
            request = ">>>XXXHELLO!{}\r\n".format(number).encode()
            stream.write(request)
            data = await stream.read_until(b'\r\n', timeout=self.timeout)
            return data[:-2]

        try:
            client = TCPClient(api)
            return await client.connect(client_handler, '127.0.0.1', 22088)
        except Exception as exc:
            self.callog.append(('connect_exc', exc))

    async def client_runner(self, api):
        f0 = api.submit(self.client_request, 200)
        f1 = api.submit(self.client_request, 500)
        f2 = api.submit(self.client_request, 100)
        f3 = api.submit(self.client_request, 150)
        f4 = api.submit(self.client_request, 250)
        try:
            result = await api.complete(f0, f1, f2, f3, f4, timeout=self.timeout)
            result = tuple(item.split(b'!')[1:] for item in sorted(result))
        except Exception as exc:
            result = exc
        self.callog.append(('result', result))
        self.stop()

    def before_start(self, api):
        api.submit(self.client_runner)


def test_network(callog):
    server = EchoTestServer(callog, 1.0)
    server.bind(22088, '127.0.0.1')
    server.start()

    print(callog)
    assert callog == [('result', (
        [b'HELLO', b'100'],
        [b'HELLO', b'150'],
        [b'HELLO', b'200'],
        [b'HELLO', b'250'],
        [b'HELLO', b'500'])
    )]


if __name__ == '__main__':
    pytest.main([__file__])


