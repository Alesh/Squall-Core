"""
Implementation of the network primitives used coroutines for async I/O.
"""
import errno
import socket
import logging
from squall.coroutine import Dispatcher, start, stop
from squall.coroutine import READ, CLEANUP
from squall.iostream import IOStream
from squall.utils import bind_sockets, Addr
from _squall import SocketAutoBuffer

logger = logging.getLogger(__name__)


class SocketStream(IOStream):
    """ Asyn soucket I/O stream.
    """

    def __init__(self, disp, sock, block_size=1024, buffer_size=16384):
        self._sock = sock
        self._sock.setblocking(0)
        autobuff = SocketAutoBuffer(disp._event_disp, sock,
                                    block_size, buffer_size)
        super().__init__(disp, autobuff)

    def abort(self):
        """ Closes a stream and releases resources immediately.
        """
        try:
            super().abort()
            self._sock.shutdown(socket.SHUT_RDWR)
        except IOError:
            pass
        finally:
            self._sock.close()


class SocketAcceptor(object):
    """ Socket connection acceptor and keeper.
    """

    def __init__(self, disp, sock,
                 on_handle, on_accept, on_listen, on_finish):
        self._disp = disp
        self._sock = sock
        self._connections = dict()
        self._sock.setblocking(0)
        self._event_disp = self._disp._event_disp
        self._addr = Addr(sock.getsockname())
        self._on_handle = on_handle
        self._on_accept = on_accept
        self._on_listen = on_listen
        self._on_finish = on_finish

    async def _conn_handler(self, conn):
        coro, _ = Dispatcher.current()
        try:
            await self._on_handle(*conn)
        finally:
            self._connections.pop(coro, None)

    def _acceptor(self, revents):
        if revents & READ:
            attempts = 16
            while attempts:
                attempts -= 1
                try:
                    sock, addr = self._sock.accept()
                    sock.setblocking(0)
                    conn = self._on_accept(self._disp, sock, Addr(addr))
                    if conn is not None:
                        coro = self._disp.spawn(self._conn_handler, conn)
                        self._connections[coro] = conn
                except IOError as exc:
                    if exc.errno == errno.ECONNABORTED:
                        continue
                    if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                        logger.error("Cannon accept incoming connection")
                        break
            return True
        else:
            if revents & CLEANUP:
                self.finish()

    def listen(self):
        """ Starts connection listening.
        """
        event_disp = self._disp._event_disp
        if not event_disp.watch_io(self._acceptor, self._sock.fileno(), READ):
            raise IOError("Cannot setup connection acceptor")
        self._on_listen(self._addr)

    def finish(self):
        """ Stops connection listening and closes all open connections.
        """
        self._disp._event_disp.cancel(self._acceptor)
        for coroconn in tuple(self._connections.keys()):
            coroconn.close()
        self._sock.close()
        self._on_finish(self._addr)


class TCPServer(object):
    """ TCP Server
    """
    def __init__(self, *, disp=None,
                 on_listen=None, on_finish=None,
                 on_handle=None, on_accept=None,
                 block_size=1024, buffer_size=16384):
        self._started = 0
        self._sockets = list()
        self._acceptors = dict()
        self._disp = disp or Dispatcher.instance()
        self._on_listen = on_listen or (lambda *args: None)
        self._on_finish = on_finish or (lambda *args: None)

        on_handle = on_handle or getattr(self, '_connection_handler', None)
        on_handle = on_handle or getattr(self, 'request_handler', None)
        assert on_handle is not None, "`request_handler` is not defined"
        self._on_handle = on_handle or (lambda *args: None)

        on_accept = on_accept or getattr(self, '_connection_factory', None)
        self._on_accept = on_accept or (lambda disp, sock, addr:
                                        (SocketStream(disp, sock, 1024, 16384),
                                         addr))

    def _add_acceptors(self, sockets):
        try:
            for sock in sockets:
                acceptor = SocketAcceptor(self._disp, sock,
                                          self._on_handle, self._on_accept,
                                          self._on_listen, self._on_finish)
                self._acceptors[sock] = acceptor
                acceptor.listen()
        except Exception:
            self.stop()
            logging.exception("Cannot setup acceptors")

    def bind(self, port, address=None, *,
             family=socket.AF_UNSPEC, backlog=128):
        """ Binds this server to the given port on the given address.
        """
        sockets = bind_sockets(port, address, family=family, backlog=backlog)
        if self._started:
            self._add_acceptors(sockets)
        else:
            self._sockets.extend(sockets)

    def start(self, port=None, address=None, **kwargs):
        assert not self._started

        def start_listening(*args):
            self._add_acceptors(self._sockets)

        if port is not None:
            family = kwargs.get('family', socket.AF_UNSPEC)
            sockets = bind_sockets(port, address, family=family,
                                   backlog=kwargs.pop('backlog', 128))
            self._sockets.extend(sockets)

        if len(self._sockets):
            self._started = 1
            self._disp._event_disp.watch_timer(start_listening, 0)
            if 'workers' in kwargs:
                self._started = 2
                start(disp=self._disp, **kwargs)
        else:
            raise RuntimeError("Nothing to start")

    def listen(self, port, address=None):
        """ Starts accepting connections on the given port.
        """
        sockets = bind_sockets(port, address)
        self._add_acceptors(sockets)

    def stop(self):
        """Stops listening for new connections and closes all presents.
        """
        for sock, acceptor in tuple(self._acceptors.items()):
            self._acceptors.pop(sock)
            acceptor.finish()
        if self._started == 2:
            stop(disp=self._disp)
