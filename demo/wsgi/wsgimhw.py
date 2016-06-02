import logging
import multiprocessing
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import WSGIGateway
from squall.backend import SCGIBackend


class WSGIServer(SCGIBackend):

    def __init__(self, port, address=None):
        gateway = WSGIGateway(self.handle_request, timeout=10)
        sockets = bind_sockets(port, address=address, backlog=256)
        super(WSGIServer, self).__init__(gateway, sockets, timeout=5.0)

    def listen(self, processes=None):

        def start_worker():
            super(WSGIServer, self).listen()
            coroutine.run()

        for _ in range(0, (processes or multiprocessing.cpu_count()) - 1):
            worker = multiprocessing.Process(target=start_worker)
            worker.start()
        start_worker()

    def handle_request(self, environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain')])
        yield b"Hello, world!"


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    WSGIServer(9090).listen(processes=2)

# $ python -O demo/wsgi/wsginhw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8080
# Transactions:              99971 hits
# Availability:              99.97 %
# Elapsed time:              24.30 secs
# Data transferred:           1.24 MB
# Response time:              0.21 secs
# Transaction rate:        4114.03 trans/sec
# Throughput:             0.05 MB/sec
# Concurrency:              875.74
# Successful transactions:       99971
# Failed transactions:              29
# Longest transaction:           15.14
# Shortest transaction:           0.00
