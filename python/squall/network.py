"""
Implementation of the network primitives used coroutines for async I/O.
"""
import errno
import socket
import logging
from abc import ABCMeta, abstractmethod
from squall.coroutine import Dispatcher, IOStream, start, stop
from squall.coroutine import READ, CLEANUP
from squall.utils import bind_sockets
from _squall import SocketAutoBuffer

logger = logging.getLogger(__name__)


class SocketStream(IOStream):
    """ Asyn soucket I/O stream.
    """

    def __init__(self, sock, block_size=1024, max_size=16384, *, disp=None):
        self._sock = sock
        self._sock.setblocking(0)
        disp = disp or Dispatcher.current()[1] or Dispatcher.instance()
        autobuff = SocketAutoBuffer(disp._event_disp, sock,
                                    block_size, max_size)
        super(SocketStream, self).__init__(disp, autobuff)

    def abort(self):
        """ Closes a stream and releases resources immediately.
        """
        try:
            super(SocketStream, self).abort()
            self._sock.shutdown(socket.SHUT_RDWR)
        except IOError:
            pass
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
        self._disp = disp or Dispatcher.current()[1] or Dispatcher.instance()
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
        if revents & READ:
            attempts = 16
            while attempts:
                attempts -= 1
                try:
                    sock, addr = self._sock.accept()
                    sock.setblocking(0)
                    conn = self._conn_factory(sock, addr)
                    self._conn[conn] = self._disp.spawn(self._coconn, *conn)
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
        self.on_listen(self._addr)

    def finish(self):
        """ Stops connection listening and closes all open connections.
        """
        self._disp._event_disp.cancel(self._acceptor)
        for coroconn in tuple(self._conn.values()):
            coroconn.close()
        self._sock.close()
        self.on_finish(self._addr)


class TCPServer(metaclass=ABCMeta):
    """ TCP Server
    """

    def __init__(self, block_size=1024, buffer_size=16384, *, disp=None):
        self._started = 0
        self._sockets = list()
        self._acceptors = dict()
        self._block_size = block_size
        self._buffer_size = buffer_size
        self._disp = disp or Dispatcher.current()[1] or Dispatcher.instance()
        self.on_listen = lambda addr: None
        self.on_finish = lambda addr: None

    def _add_acceptors(self, sockets):
        try:
            for sock in sockets:
                acceptor = SocketAcceptor(sock, self.handle_stream,
                                          self._connection_factory,
                                          disp=self._disp)
                acceptor.on_listen = self.on_listen
                acceptor.on_finish = self.on_finish
                self._acceptors[sock] = acceptor
                acceptor.listen()
        except Exception:
            self.stop()
            logging.exception("Cannot setup acceptors")

    def _connection_factory(self, sock, addr):
        return (SocketStream(sock, self._block_size,
                             self._buffer_size, disp=self._disp), addr)

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
                                   backlog=kwargs.get('backlog', 128))
            self._sockets.extend(sockets)

        if len(self._sockets):
            self._started = 1
            self._disp._event_disp.watch_timer(start_listening, 0)
            if 'worker' in kwargs:
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


    @abstractmethod
    async def handle_stream(self, stream, addr):
        """ Should be implemented to handle a async stream
        from an incoming connection.
        """
