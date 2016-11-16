import sys
import socket
import logging
from functools import partial
from tornado.netutil import bind_sockets
from squall.coroutine import EventDispatcher


def echo_handler(event_disp, socket_, revents):
    if revents & event_disp.READ:
        data = socket_.recv(1024)
        if data:
            socket_.send(data)
            return True
        else:
            logging.warning("Connection reset by peer")
    socket_.shutdown(socket.SHUT_RDWR)
    socket_.close()


def echo_acceptor(event_disp, socket_, revents):
    if revents & event_disp.READ:
        client_socket, _ = socket_.accept()
        client_socket.setblocking(0)
        callback = partial(echo_handler, event_disp, client_socket)
        event_disp.watch_io(callback, client_socket.fileno(), event_disp.READ)
        return True
    socket_.shutdown(socket.SHUT_RDWR)
    socket_.close()


def echo_server(port):
    event_disp = EventDispatcher()
    for listen_socket in bind_sockets(port, backlog=128, reuse_port=True):
        listen_socket.setblocking(0)
        callback = partial(echo_acceptor, event_disp, listen_socket)
        event_disp.watch_io(callback, listen_socket.fileno(), event_disp.READ)
    event_disp.start()

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 22077
    echo_server(port)
