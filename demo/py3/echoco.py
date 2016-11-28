import sys
import errno
import socket
import logging
from squall.coroutine import ready,  READ, WRITE
from squall.coroutine import start, stop, spawn
from squall.utils import bind_sockets, timeout_gen

logger = logging.getLogger('echoco.py')


async def echo_handler(connection_socket, address):
    try:
        while True:
            timeout = timeout_gen(15)
            fileno = connection_socket.fileno()
            await ready(fileno, READ, timeout=next(timeout))
            data = connection_socket.recv(1024)
            if data:
                await ready(fileno, WRITE, timeout=next(timeout))
                connection_socket.send(data)
            else:
                raise ConnectionResetError("Connection reset by peer")
    except IOError as exc:
        logger.warning("{} Connection fail: {}".format(address, exc))


async def echo_acceptor(listen_socket, address):
    connections = dict()
    listen_socket.setblocking(0)
    fileno = listen_socket.fileno()
    logger.info("{} Established echo listener".format(address))

    async def serve_connection(*args):
        connection_socket, address = args
        connection_socket.setblocking(0)
        logger.info("{} Accepted connection".format(address))
        try:
            await echo_handler(connection_socket, address)
        finally:
            connections.pop(args)
            if connection_socket:
                try:
                    connection_socket.shutdown(socket.SHUT_RDWR)
                finally:
                    connection_socket.close()
            logger.info("{} Connection has closed".format(address))

    try:
        while True:
            await ready(fileno, READ)
            while True:
                try:
                    args = listen_socket.accept()
                    connections[args] = spawn(serve_connection, *args)
                except IOError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        break
                    raise exc

    except IOError as exc:
        logger.error("{} Listenner fail: {}".format(address, exc))
    finally:
        logger.info("{} Finished echo listener".format(address))
        listen_socket.shutdown(socket.SHUT_RDWR)
        listen_socket.close()


def main():

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    for socket_ in bind_sockets(port, 'localhost'):
        spawn(echo_acceptor, socket_, socket_.getsockname())
    try:
        start()
    except KeyboardInterrupt:
        stop()


if __name__ == '__main__':
    main()
