""" Squall callback classes
"""
import logging
import asyncio


class CannotSetupWatching(RuntimeError):
    def __init__(self, msg=None):
        super().__init__(msg or "Set up an event watching")


class EventLoop(object):
    """ Event loop implementation on the asyncio event loops
    """
    READ    = 0x00000001
    WRITE   = 0x00000002
    TIMEOUT = 0x00000004
    SIGNAL  = 0x00000008
    ERROR   = 0x00000010
    CLEANUP = 0x00000020
    BUFFER  = 0x00000040

    def __init__(self):
        self._fds = dict()
        self._signals = dict()
        self._running = False
        self._loop = asyncio.get_event_loop()

    def _handle_signal(self, signum):
        for callback in tuple(self._signals[signum]):
            self._loop.call_soon(callback, True)

    @property
    def running(self):
        """ Returns `True` if tis is active.
        """
        return self._running

    def start(self):
        """ Starts the event dispatching.
        """
        logging.info("Using asyncio based callback classes")
        self._running = True
        self._loop.run_forever()
        self._running = False

    def stop(self):
        """ Stops the event dispatching.
        """
        self._loop.stop()

    def setup_io(self, callback, fd, events):
        """ Setup to run the `callback` when I/O device with
        given `fd` would be ready to read or/and write.
        Returns handle for using with `EventLoop.update_io` and `EventLoop.cancel_io`
        """
        if events & (self.READ | self.WRITE):
            if events & self.READ:
                self._loop.add_reader(fd, callback, self.READ)
            if events & self.WRITE:
                self._loop.add_writer(fd, callback, self.WRITE)
            self._fds[fd] = [callback, events]
            return fd
        raise CannotSetupWatching()

    def update_io(self, handle, events):
        """ Updates call settings for callback which was setup with `EventLoop.setup_io`.
        """
        fd = handle
        if fd in self._fds:
            callback, _events = self._fds[fd]
            if _events != events:
                if (events & self.READ) and not _events & self.READ:
                    self._loop.add_reader(fd, callback, self.READ)
                elif (_events & self.READ) and not events & self.READ:
                    self._loop.remove_reader(fd)
                if (events & self.WRITE) and not _events & self.WRITE:
                    self._loop.add_writer(fd, callback, self.WRITE)
                elif (_events & self.WRITE) and not events & self.WRITE:
                    self._loop.remove_writer(fd)
                self._fds[fd][1] = events
                return True
        return False

    def cancel_io(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_io`.
        """
        fd = handle
        if fd in self._fds:
            _, events = self._fds.pop(fd)
            if events & self.READ:
                self._loop.remove_reader(fd)
            if events & self.WRITE:
                self._loop.remove_writer(fd)
            return True
        return False

    def setup_timer(self, callback, seconds):
        """ Setup to run the `callback` after a given `seconds` elapsed.
        Returns handle for using with `EventLoop.cancel_timer`
        """
        deadline = self._loop.time() + seconds
        exc = TimeoutError("Timed out")
        handle = self._loop.call_at(deadline, callback, exc)
        if handle is not None:
            return handle
        raise CannotSetupWatching()

    def cancel_timer(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_timer`.
        """
        if isinstance(handle, asyncio.Handle):
            handle.cancel()
            return True
        return False

    def setup_signal(self, callback, signum):
        """ Setup to run the `callback` when system signal with a given `signum` received.
        Returns handle for using with `EventLoop.cancel_signal`
        """
        if signum not in self._signals:
            self._loop.add_signal_handler(signum, self._handle_signal, signum)
            self._signals[signum] = list()
        self._signals[signum].append(callback)
        return signum, callback

    def cancel_signal(self, handle):
        """ Cancels callback which was setup with `EventLoop.setup_signal`.
        """
        signum, callback = handle
        if signum in self._signals:
            self._signals[signum].remove(callback)
            return True
        return False
