import logging
import multiprocessing
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import SAGIGateway
from squall.backend import SCGIBackend


class SAGIServer(SCGIBackend):

    def __init__(self, port, address=None):
        gateway = SAGIGateway(self.handle_request)
        sockets = bind_sockets(port, address=address, backlog=256)
        super(SAGIServer, self).__init__(gateway, sockets, timeout=15.0)

    def listen(self, processes=None):

        def start_worker():
            super(SAGIServer, self).listen()
            coroutine.run()

        for _ in range(0, (processes or multiprocessing.cpu_count()) - 1):
            worker = multiprocessing.Process(target=start_worker)
            worker.start()
        start_worker()

    async def handle_request(self, environ, start_response):
        write = start_response('200 OK', [('Content-Type', 'text/plain')])
        await write(b"Hello, world!")


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    SAGIServer(9000).listen(processes=2)

# $ python -O demo/scgi/sagimhw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:              99950 hits
# Availability:              99.95 %
# Elapsed time:              24.07 secs
# Data transferred:           1.25 MB
# Response time:              0.21 secs
# Transaction rate:        4152.47 trans/sec
# Throughput:             0.05 MB/sec
# Concurrency:              875.67
# Successful transactions:       99950
# Failed transactions:              50
# Longest transaction:            7.31
# Shortest transaction:           0.00
