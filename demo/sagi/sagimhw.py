import logging
import multiprocessing
from squall import coroutine
from squall.network import bind_sockets
from gateway import SAGIGateway


class SAGIServer(SAGIGateway):

    def __init__(self):
        super(SAGIServer, self).__init__(
            self.handle_request, timeout=15.0)

    def start(self, port, address=None, processes=None):
        sockets = bind_sockets(port, address=address, backlog=256)

        def start_worker():
            super(SAGIServer, self).start(sockets)
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
    SAGIServer().start(9000, processes=2)

# Tornado
# $ python -O demo/sagi/sagimhw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:              99998 hits
# Availability:             100.00 %
# Elapsed time:              22.54 secs
# Data transferred:           1.24 MB
# Response time:              0.20 secs
# Transaction rate:        4436.47 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              865.14
# Successful transactions:       99998
# Failed transactions:               2
# Longest transaction:            7.27
# Shortest transaction:           0.00


# $ siege -c 400 -b -r 100 http://127.0.0.1:8000
# Transactions:              40000 hits
# Availability:             100.00 %
# Elapsed time:               7.07 secs
# Data transferred:           0.50 MB
# Response time:              0.06 secs
# Transaction rate:        5657.71 trans/sec
# Throughput:             0.07 MB/sec
# Concurrency:              365.58
# Successful transactions:       40000
# Failed transactions:               0
# Longest transaction:            1.25
# Shortest transaction:           0.00


# CCX
# $ python -O demo/sagi/sagimhw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:             100000 hits
# Availability:             100.00 %
# Elapsed time:              17.43 secs
# Data transferred:           1.24 MB
# Response time:              0.15 secs
# Transaction rate:        5737.23 trans/sec
# Throughput:             0.07 MB/sec
# Concurrency:              883.11
# Successful transactions:      100000
# Failed transactions:               0
# Longest transaction:            7.07
# Shortest transaction:           0.00


# siege -c 400 -b -r 100 http://127.0.0.1:8000
# Transactions:              40000 hits
# Availability:             100.00 %
# Elapsed time:               5.19 secs
# Data transferred:           0.50 MB
# Response time:              0.05 secs
# Transaction rate:        7707.13 trans/sec
# Throughput:             0.10 MB/sec
# Concurrency:              355.91
# Successful transactions:       40000
# Failed transactions:               0
# Longest transaction:            1.24
# Shortest transaction:           0.00
# Shortest transaction:           0.00
