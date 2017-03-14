""" Network classes
"""
from socket import SocketType

from squall.core.abc import StreamHandler
from squall.core.abc import Switcher as AbcSwitcher
from squall.core.abc import TCPServer as AbcTCPServer
from squall.core.native.iostream import IOStream
from squall.core.native.switching import Dispatcher

try:
    from squall.core.native.cb.tornado_ import SocketAutoBuffer
    from squall.core.native.cb.tornado_ import SocketAcceptor, bind_sockets
except ImportError:
    from squall.core.native.cb.asyncio_ import SocketAutoBuffer
    from squall.core.native.cb.asyncio_ import SocketAcceptor, bind_sockets


class _SocketStream(IOStream):
    """ Server socket stream
    """

    def __init__(self, disp: Dispatcher, switcher,
                 socket_, block_size, buffer_size):
        socket_.setblocking(0)
        super().__init__(switcher, SocketAutoBuffer(disp._loop, socket_,
                                                    block_size, buffer_size))


class TCPServer(AbcTCPServer):
    """ Native implementation of the async TCP server
    """

    class ConnectionsManager(AbcSwitcher):
        """ Connections manager / coroutine switcher
        """

        def __init__(self, disp: Dispatcher,
                     stream_handler: StreamHandler,
                     block_size: int, buffer_size: int):
            self._disp = disp
            self._connections = dict()
            self._block_size = block_size
            self._buffer_size = buffer_size
            self._stream_handler = stream_handler

        def accept(self, socket_: SocketType, address: str):
            """ Accepts incoming connection.
            """
            stream = _SocketStream(self._disp, self, socket_,
                                   self._block_size, self._buffer_size)
            coro = self._stream_handler(self._disp, stream, address)
            self._connections[coro] = stream
            self.switch(coro, None)

        def close_all(self):
            """ Closes all client connection
            """
            for coro in tuple(self._connections.keys()):
                self.switch(coro, GeneratorExit())

        @property
        def current(self):
            """ See more: `AbcSwitcher.current` """
            return self._disp.current

        def switch(self, coro, value):
            """ See more: `AbcSwitcher.switch` """
            still_active = self._disp.switch(coro, value)
            if not still_active:
                stream = self._connections.pop(coro)
                stream.close()


    def __init__(self, stream_handler, block_size=1024, buffer_size=65536):
        self._disp = None  # type: Dispatcher
        self._sockets = dict()
        self._acceptors = dict()
        self._cm = None  # type: self.ConnectionsManager
        self._cm_args = (stream_handler, block_size, buffer_size)

    @property
    def active(self):
        """ See more: `AbcTCPServer.active` """
        return self._disp is not None

    def bind(self, port, address=None, *, backlog=128, reuse_port=False):
        """ See more: `AbcTCPServer.bind` """
        for socket_ in bind_sockets(port, address, backlog=backlog, reuse_port=reuse_port):
            if self.active:
                acceptor = SocketAcceptor(self._disp._loop, socket_, self._connections.accept)
                if (port, address) not in self._acceptors:
                    self._acceptors[(port, address)] = list()
                self._acceptors[(port, address)].append(acceptor)
            else:
                if (port, address) not in self._sockets:
                    self._sockets[(port, address)] = list()
                self._sockets[(port, address)].append(socket_)

    def unbind(self, port, address=None):
        """ See more: `AbcTCPServer.unbind` """
        if self.active:
            for acceptor in self._acceptors.pop((port, address), []):
                acceptor.close()
        elif (port, address) in self._sockets:
            self._sockets.pop((port, address))

    def before_start(self, disp):
        """ See more: `AbcTCPServer.before_start` """

    def start(self, num_processes=1):
        """ See more: `AbcTCPServer.start` """
        self._disp = Dispatcher()
        self._cm = self.ConnectionsManager(self._disp, *self._cm_args)
        self.before_start(self._disp)
        assert num_processes == 1  # ToDo: multiprocessed TCP server
        for (port, address), sockets in self._sockets.items():
            for socket_ in sockets:
                acceptor = SocketAcceptor(self._disp._loop, socket_, self._cm.accept)
                if (port, address) not in self._acceptors:
                    self._acceptors[(port, address)] = list()
                self._acceptors[(port, address)].append(acceptor)
        self._sockets.clear()
        self._disp.start()
        self._disp = None

    def stop(self):
        """ See more: `AbcTCPServer.stop` """
        if self.active:
            self._sockets.clear()
            for (port, address) in tuple(self._acceptors.keys()):
                self.unbind(port, address)
            self._cm.close_all()
            self._disp.stop()
