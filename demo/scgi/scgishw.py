import logging
from squall.scgi import Server


class ServerHW(Server):

    def __init__(self):
        super(ServerHW, self).__init__(self.handle_request)

    async def handle_request(self, environ, start_response):
        write = start_response('200 OK', [('Content-Type', 'text/plain')])
        await write(b"Hello, world!")


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    server = ServerHW()
    server.bind(9000, '127.0.0.1', backlog=256)
    server.start()


# Tornado
# $ python -O demo/sagi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1
# Transactions:              99370 hits
# Availability:              99.37 %
# Elapsed time:              34.40 secs
# Data transferred:           1.34 MB
# Response time:              0.29 secs
# Transaction rate:        2888.66 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              830.02
# Successful transactions:       99370
# Failed transactions:             630
# Longest transaction:           15.11
# Shortest transaction:           0.00

# $ python -O demo/sagi/sagishw.py
# $ siege -c 400 -b -r 100 http://127.0.0.1
# Transactions:              39999 hits
# Availability:             100.00 %
# Elapsed time:              13.31 secs
# Data transferred:           0.50 MB
# Response time:              0.12 secs
# Transaction rate:        3005.18 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              345.76
# Successful transactions:       39999
# Failed transactions:               1
# Longest transaction:            3.48
# Shortest transaction:           0.00


# CCX
# $ python -O demo/sagi/sagishw.py
# $ siege -c 1000 -b -r 100 http://127.0.0.1
# Transactions:              99973 hits
# Availability:              99.97 %
# Elapsed time:              21.13 secs
# Data transferred:           1.24 MB
# Response time:              0.17 secs
# Transaction rate:        4731.33 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              801.69
# Successful transactions:       99973
# Failed transactions:              27
# Longest transaction:           15.29
# Shortest transaction:           0.00

# $ siege -c 400 -b -r 100 http://127.0.0.1
# Transactions:              40000 hits
# Availability:             100.00 %
# Elapsed time:               7.96 secs
# Data transferred:           0.50 MB
# Response time:              0.07 secs
# Transaction rate:        5025.13 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              345.96
# Successful transactions:       40000
# Failed transactions:               0
# Longest transaction:            3.29
# Shortest transaction:           0.00
