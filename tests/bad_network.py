import pytest
import socket
from time import time
from functools import partial
from squall.core import TCPServer, SocketStream
from squall.core.switching import Awaitable
from squall.core.utils import timeout_gen



class TCPClient(object):
    """ Native implementation of the async TCP client
    """

    def __init__(self, disp, block_size=1024, buffer_size=65536):
        self._disp = disp
        self._stream_params = (block_size, buffer_size)

    def connect(self, stream_handler, host, port, *, timeout=None):
        """ See for detail `AbcTCPClient.connect` """
        return self._ConnectAwaitable(self._disp, stream_handler,
                                      host, port, timeout, *self._stream_params)

    class _ConnectAwaitable(Awaitable):
        """ Awaitable for `TCPClient.connect` """

        def __init__(self, disp, stream_handler, host, port, timeout, block_size, buffer_size):
            self._disp = disp
            self._loop = disp._loop
            self._block_size = block_size
            self._buffer_size = buffer_size
            self._stream_handler = stream_handler
            timeout = timeout or 0
            timeout = timeout if timeout >= 0 else -1
            assert isinstance(timeout, (int, float))
            assert isinstance(host, str)
            assert isinstance(port, int)
            self._handles = []
            self._address = (host, port)
            super().__init__(host, port, timeout)

        def on_connect(self, socket_, revents):

            def done_callback(future):
                try:
                    result = future.result()
                    self._callback(result if result is not None else True)
                except BaseException as exc:
                    self._callback(exc)

            self.cancel()

            if isinstance(revents, Exception):
                try:
                    socket_.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                finally:
                    socket_.close()
                self._callback(ConnectionError("Cannon connect"))
            else:
                stream = SocketStream(self._disp, socket_, self._block_size, self._buffer_size)
                future = self._disp.submit(self._stream_handler, stream, self._address)

                if future.done():
                    done_callback(future)
                else:
                    future.add_done_callback(done_callback)
                    self._handles.append(future)

        def setup(self, host, port, timeout):
            timeout_exc = TimeoutError("I/O timeout")
            if timeout < 0:
                return timeout_exc,
            try:
                socket_ = socket.socket()
                socket_.setblocking(0)
                socket_.settimeout(0)
                self._handles.append(self._loop.setup_io(partial(self.on_connect, socket_),
                                                         socket_.fileno(), self._loop.WRITE))
                if timeout > 0:
                    def callback_(revents):
                        self.on_connect(self._callback, socket_, timeout_exc)
                    self._handles.append(self._loop.setup_timer(callback_, timeout))
                else:
                    self._handles.append(None)
                try:
                    socket_.connect(self._address)
                except BlockingIOError:
                    pass
            except BaseException as exc:
                return exc,
            return None,

        def cancel(self):
            if len(self._handles) == 2:
                ready, timeout = self._handles
                self._loop.cancel_io(ready)
                if timeout is not None:
                    self._loop.cancel_timer(timeout)
            elif len(self._handles) == 1:
                future = self._handles[0]
                if future.running():
                    future.cancel()
            self._handles.clear()


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
            result = [item.result() for item in result]
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

