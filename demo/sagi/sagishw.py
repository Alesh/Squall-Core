import logging
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import SAGIGateway
from squall.backend import SCGIBackend


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

# $ python -O demo/scgi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:              99446 hits
# Availability:              99.45 %
# Elapsed time:              39.04 secs
# Data transferred:           1.34 MB
# Response time:              0.34 secs
# Transaction rate:        2547.28 trans/sec
# Throughput:             0.03 MB/sec
# Concurrency:              873.63
# Successful transactions:       99446
# Failed transactions:             554
# Longest transaction:           15.59
# Shortest transaction:           0.00
