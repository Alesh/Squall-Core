import logging
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import SAGIGateway, SCGIBackend


class SAGIServer(SCGIBackend):

    def __init__(self, port, address=None):
        gateway = SAGIGateway(self.handle_request)
        sockets = bind_sockets(port, address=address, backlog=256)
        super(SAGIServer, self).__init__(gateway, sockets, timeout=15.0)

    def listen(self):
        super(SAGIServer, self).listen()
        coroutine.run()

    async def handle_request(self, environ, start_response):
        write = start_response('200 OK', [('Content-Type', 'text/plain')])
        await write(b"Hello, world!")


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    SAGIServer(9000).listen()

# Tornado
# $ python -O demo/sagi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:              99220 hits
# Availability:              99.22 %
# Elapsed time:              36.56 secs
# Data transferred:           1.37 MB
# Response time:              0.27 secs
# Transaction rate:        2713.89 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              736.65
# Successful transactions:       99220
# Failed transactions:             780
# Longest transaction:           15.33
# Shortest transaction:           0.00


# CCX
# $ python -O demo/sagi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:              99998 hits
# Availability:             100.00 %
# Elapsed time:              21.01 secs
# Data transferred:           1.24 MB
# Response time:              0.16 secs
# Transaction rate:        4759.54 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              738.01
# Successful transactions:       99998
# Failed transactions:               2
# Longest transaction:           16.68
# Shortest transaction:           0.00