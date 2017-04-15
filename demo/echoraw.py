""" Sample "Echo server" based only on base classes
"""
import errno
import logging
import socket
import sys
from signal import SIGINT

from squall.core import Dispatcher as API
from squall.core.switching import timeout_gen
from squall.core.networking import Addr, bind_sockets


async def echo_handler(api, connection_socket, addr):
    try:
        while True:
            timeout = timeout_gen(15)
            fileno = connection_socket.fileno()
            await api.ready(fileno, api.READ, timeout=next(timeout))
            data = connection_socket.recv(1024)
            if data:
                await api.ready(fileno, api.WRITE, timeout=next(timeout))
                connection_socket.send(data)
            else:
                raise ConnectionResetError("Connection reset by peer")
            break
    except IOError as exc:
        logging.warning("[{}]Connection fail: {}".format(addr, exc))


async def echo_acceptor(api, listen_socket):
    connections = dict()
    listen_socket.setblocking(0)
    fileno = listen_socket.fileno()
    addr = Addr(listen_socket.getsockname())
    logging.info("[{}]Established echo listener".format(addr))

    async def serve_connection(api, connection_socket, address):
        addr = Addr(address)
        key = (connection_socket, address)
        connection_socket.setblocking(0)
        logging.info("[{}]Accepted connection".format(addr))
        try:
            await echo_handler(api, connection_socket, addr)
        finally:
            connections.pop(key)
            if connection_socket:
                try:
                    connection_socket.shutdown(socket.SHUT_RDWR)
                except IOError:
                    pass
                finally:
                    connection_socket.close()
            logging.info("[{}]Connection has closed".format(addr))

    try:
        while True:
            try:
                await api.ready(fileno, api.READ, timeout=1.0)
                while True:
                    try:
                        args = listen_socket.accept()
                        connections[args] = api.submit(serve_connection, *args)
                    except IOError as exc:
                        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                            break
                        raise exc
            except TimeoutError:
                continue

    except IOError as exc:
        logging.error("[{}]Listenner fail: {}".format(addr, exc))
    finally:
        logging.info("[{}]Finished echo listener".format(addr))
        try:
            listen_socket.shutdown(socket.SHUT_RDWR)
        except IOError:
            pass
        finally:
            listen_socket.close()


async def terminator(api):
    try:
        await api.signal(SIGINT)
        print("Got SIGINT!")
    finally:
        api.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)

    api = API()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    for socket_ in bind_sockets(port):
        api.submit(echo_acceptor, socket_)
    api.submit(terminator)
    api.start()
