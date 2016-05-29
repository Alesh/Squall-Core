import logging
from squall import coroutine
from squall.network import bind_sockets
from squall.gateways import SCGIAcceptor, SCGIGateway


class SCGIBackend(SCGIAcceptor):

    def __init__(self, port, address=None):
        sockets = bind_sockets(port, address=address, backlog=256)
        gateway = SCGIGateway(self.handle_request, timeout=5.0)
        super(SCGIBackend, self).__init__(gateway, sockets)

    def listen(self):
        super(SCGIBackend, self).listen()
        coroutine.run()

    async def handle_request(self, environ, start_response):
        write = start_response('200 OK', [('Content-Type', 'text/plain')])
        await write(b"Hello, world!")


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    SCGIBackend(9000).listen()

# $ python -O demo/scgi/scgiapp.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8000
# Transactions:              99173 hits
# Availability:              99.17 %
# Elapsed time:              38.99 secs
# Data transferred:           1.37 MB
# Response time:              0.32 secs
# Transaction rate:        2543.55 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              824.30
# Successful transactions:       99173
# Failed transactions:             827
# Longest transaction:           17.34
# Shortest transaction:           0.00
