"""
Implementation of the network primitives used coroutines for async I/O.
"""
import os
import errno
import socket
import logging
from squall.coroutine import Dispatcher, IOStream, spawn
from _squall import SocketAutoBuffer

logger = logging.getLogger(__name__)


class SocketStream(IOStream):
    """ Asyn soucket I/O stream.
    """

    def __init__(self, sock, block_size=1024, max_size=16384, *, disp=None):
        self._sock = sock
        disp = disp or Dispatcher.instance()
        autobuff = SocketAutoBuffer(disp._event_disp, sock,
                                    block_size, max_size)
        super(SocketStream, self).__init__(disp, autobuff)

    def close(self):
        """ Closes a strean and releases resourses.
        """
        try:
            super(SocketStream, self).close()
            self._sock.shutdown(socket.SHUT_RDWR)
        finally:
            self._sock.close()


class SocketAcceptor(object):
    """ Socket connection acceptor and keeper.
    """

    def __init__(self, sock, connection_handler,
                 connection_factory, *, disp=None):
        self._sock = sock
        self._conn = dict()
        self._sock.setblocking(0)
        self._conn_handler = connection_handler
        self._conn_factory = connection_factory
        self._disp = disp or Dispatcher.instance()
        self._event_disp = self._disp._event_disp
        self._addr = sock.getsockname()
        self.on_listen = lambda addr: None
        self.on_finish = lambda addr: None

    async def _coconn(self, *conn):
        try:
            await self._conn_handler(*conn)
        finally:
            self._conn.pop(conn, None)

    def _acceptor(self, revents):
        if revents & self._event_disp.READ:
            attempts = 16
            while attempts:
                attempts -= 1
                try:
                    sock, addr = self._sock.accept()
                    sock.setblocking(0)
                    conn = self._conn_factory(sock, addr)
                    self._conn[conn] = spawn(self._coconn, *conn)
                except IOError as exc:
                    if exc.errno == errno.ECONNABORTED:
                        continue
                    if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                        logger.error("Cannon accept incoming connection")
                        break
            return True
        else:
            if revents & self._event_disp.CLEANUP:
                self.finish()

    def listen(self):
        """ Starts connection listening.
        """
        if not self._event_disp.watch_io(self._acceptor,
                                         self._sock.fileno(),
                                         self._event_disp.READ):
            raise RuntimeError("Cannot setup connection acceptor")
        self.on_listen(self._addr)

    def finish(self):
        """ Stops connection listening and closes all open connections.
        """
        self._event_disp.cancel(self._acceptor)
        for coroconn in tuple(self._conn.values()):
            coroconn.close()
        self._sock.close()
        self.on_finish(self._addr)


# utility functions


def bind_sockets(port, address=None, *,
                 family=socket.AF_UNSPEC,
                 backlog=128, flags=socket.AI_PASSIVE):
    results = list()
    for args in set(socket.getaddrinfo(address or None, port, family,
                                       socket.SOCK_STREAM, 0, flags)):
        try:
            socket_ = socket.socket(*args[:3])
            if os.name != 'nt':
                socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if args[0] == socket.AF_INET6 and hasattr(socket, "IPPROTO_IPV6"):
                socket_.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        except socket.error:
            logger.error("Cannot bind socket for: {}".format(args[:3]))
            continue
        socket_.bind(args[4])
        socket_.listen(backlog)
        results.append(socket_)
    if len(results) == 0:
        raise RuntimeError("Cannot bind any sockets for {}".format(args))
    return results




