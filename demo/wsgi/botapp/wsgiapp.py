import sys
import logging
import multiprocessing
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import WSGIGateway
from squall.backend import SCGIBackend
from app import app


class WSGIServer(SCGIBackend):

    def __init__(self, port, address=None):
        gateway = WSGIGateway(app, timeout=10)
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

if __name__ == '__main__':

    processes = 1
    if len(sys.argv) == 2:
        try:
            processes = int(sys.argv[1])
        except:
            pass

    logging.basicConfig(level=logging.INFO)
    WSGIServer(9090).listen(processes)

# $ python demo/wsgi/botapp/wsgiapp.py
# siege -c 1000 -b -r 100 http://127.0.0.1:8080/hello/alesh
# Transactions:              99411 hits
# Availability:              99.41 %
# Elapsed time:              49.95 secs
# Data transferred:           1.91 MB
# Response time:              0.44 secs
# Transaction rate:        1990.21 trans/sec
# Throughput:             0.04 MB/sec
# Concurrency:              883.77
# Successful transactions:       99411
# Failed transactions:             589
# Longest transaction:           15.78
# Shortest transaction:           0.00


# $ python demo/wsgi/botapp/wsgiapp.py 2
# siege -c 1000 -b -r 100 http://127.0.0.1:8080/hello/alesh
# Transactions:              99742 hits
# Availability:              99.74 %
# Elapsed time:              28.94 secs
# Data transferred:           1.86 MB
# Response time:              0.26 secs
# Transaction rate:        3446.51 trans/sec
# Throughput:             0.06 MB/sec
# Concurrency:              903.48
# Successful transactions:       99742
# Failed transactions:             258
# Longest transaction:            7.33
# Shortest transaction:           0.00
