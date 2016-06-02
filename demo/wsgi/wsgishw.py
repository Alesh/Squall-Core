import logging
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import WSGIGateway
from squall.backend import SCGIBackend


class WSGIServer(SCGIBackend):

    def __init__(self, port, address=None):
        gateway = WSGIGateway(self.handle_request, timeout=10)
        sockets = bind_sockets(port, address=address, backlog=256)
        super(WSGIServer, self).__init__(gateway, sockets, timeout=5.0)

    def listen(self):
        super(WSGIServer, self).listen()
        coroutine.run()

    def handle_request(self, environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain')])
        yield b"Hello, world!"


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    WSGIServer(9090).listen()

# $ python -O demo/wsgi/wsgishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1:8080
# Transactions:              99121 hits
# Availability:              99.12 %
# Elapsed time:              39.01 secs
# Data transferred:           1.39 MB
# Response time:              0.32 secs
# Transaction rate:        2540.91 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              811.13
# Successful transactions:       99121
# Failed transactions:             879
# Longest transaction:           16.08
# Shortest transaction:           0.00
