""" Squall callback classes
"""
from .events import READ, WRITE, TIMEOUT, SIGNAL, ERROR, CLEANUP, BUFFER
from .events import EventLoop, CannotSetupWatching, SocketBuffer, FileBuffer
