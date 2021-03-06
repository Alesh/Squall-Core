"""
`squall.core` contains core classes what using to implement
the cooperative multitasking based on event-driven switching
async/await coroutines.
"""
from squall.core.switching import Dispatcher, Awaitable  # noqa
from squall.core.iostream import SocketStream, FileStream  # noqa
from squall.core.network import TCPServer, TCPClient  # noqa
