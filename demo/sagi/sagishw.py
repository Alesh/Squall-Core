import logging
from squall import coroutine
from squall.network import bind_sockets
from gateway import SAGIGateway


class SAGIServer(SAGIGateway):

    def __init__(self):
        super(SAGIServer, self).__init__(
            self.handle_request, timeout=15.0)

    def start(self, port, address=None):
        sockets = bind_sockets(port, address=address, backlog=256)
        super(SAGIServer, self).start(sockets)
        coroutine.run()

    async def handle_request(self, environ, start_response):
        write = start_response('200 OK', [('Content-Type', 'text/plain')])
        await write(b"Hello, world!")


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    SAGIServer().start(9000)

# Tornado
# $ python -O demo/sagi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1
# Transactions:              99732 hits
# Availability:              99.73 %
# Elapsed time:              41.11 secs
# Data transferred:           1.28 MB
# Response time:              0.30 secs
# Transaction rate:        2425.98 trans/sec
# Throughput:             0.03 MB/sec
# Concurrency:              718.42
# Successful transactions:       99732
# Failed transactions:             268
# Longest transaction:           15.12
# Shortest transaction:           0.00

# $ python -O demo/sagi/sagishw.py
# $ siege -c 400 -b -r 100 http://127.0.0.1
# Transactions:              40000 hits
# Availability:             100.00 %
# Elapsed time:              13.27 secs
# Data transferred:           0.50 MB
# Response time:              0.11 secs
# Transaction rate:        3014.32 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              326.91
# Successful transactions:       40000
# Failed transactions:               0
# Longest transaction:            7.07
# Shortest transaction:           0.02



# CCX
# $ python -O demo/sagi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1
# Transactions:              99667 hits
# Availability:              99.67 %
# Elapsed time:              20.21 secs
# Data transferred:           1.30 MB
# Response time:              0.17 secs
# Transaction rate:        4931.57 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              821.48
# Successful transactions:       99667
# Failed transactions:             333
# Longest transaction:           15.69
# Shortest transaction:           0.00



# $ siege -c 400 -b -r 100 http://127.0.0.1
# Transactions:              40000 hits
# Availability:             100.00 %
# Elapsed time:               7.83 secs
# Data transferred:           0.50 MB
# Response time:              0.07 secs
# Transaction rate:        5108.56 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              339.80
# Successful transactions:       40000
# Failed transactions:               0
# Longest transaction:            3.46
# Shortest transaction:           0.00
