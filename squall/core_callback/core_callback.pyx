import signal
import logging
cimport Squall
from cpython.ref cimport PyObject
from Squall cimport PyEventLoop, PyAutoBuffer, Event


cdef class EventLoop:
    """ Event loop
    """
    READ = Event.Read
    WRITE = Event.Write
    TIMEOUT = Event.Timeout
    SIGNAL = Event.Signal
    ERROR = Event.Error
    CLEANUP = Event.Cleanup

    cdef PyEventLoop* c_loop

    def __cinit__(self):
        self.c_loop = new PyEventLoop()

    def __dealloc__(self):
        del self.c_loop

    def is_running(self):
        """ Returns `True` if tis is active.
        """
        return self.c_loop.running()

    def start(self):
        """ Starts the event dispatching.
        """
        logging.info("Using cython/libev based callback classes")
        self.setup_signal(lambda revents: self.stop() , signal.SIGINT)
        self.c_loop.start()

    def stop(self):
        """ Stops the event dispatching.
        """
        self.c_loop.stop()

    def setup_io(self, callback, int fd, int mode):
        """ Setup to run the `callback` when I/O device with
        given `fd` would be ready to read or/and write.
        Returns handle for using with `EventLoop.update_io` and `EventLoop.cancel_io`
        """
        if self.c_loop.setup_io(<PyObject*>callback, fd, mode):
            return callback
        return None

    def update_io(self, callback, int events):
        """ Updates call settings for callback which was setup with `EventLoop.setup_io`.
        """
        return self.c_loop.update_io(<PyObject*>callback, events)

    def cancel_io(self, callback):
        """ Cancels callback which was setup with `EventLoop.setup_io`.
        """
        return self.c_loop.cancel_io(<PyObject*>callback)

    def setup_timer(self, callback, double seconds):
        """ Setup to run the `callback` after a given `seconds` elapsed.
        Returns handle for using with `EventLoop.cancel_timer`
        """
        if self.c_loop.setup_timer(<PyObject*>callback, seconds):
            return callback
        return None

    def update_timer(self, callback, double seconds):
        """ Updates call settings for callback which was setup with `EventLoop.setup_timer`.
        """
        return self.c_loop.update_timer(<PyObject*>callback, seconds)

    def cancel_timer(self, callback):
        """ Cancels callback which was setup with `EventLoop.setup_timer`.
        """
        return self.c_loop.cancel_timer(<PyObject*>callback)

    def setup_signal(self, callback, int signum):
        """ Setup to run the `callback` when system signal with a given `signum` received.
        Returns handle for using with `EventLoop.cancel_signal`
        """
        if self.c_loop.setup_signal(<PyObject*>callback, signum):
            return callback
        return None

    def cancel_signal(self, callback):
        """ Cancels callback which was setup with `EventLoop.setup_signal`.
        """
        return self.c_loop.cancel_signal(<PyObject*>callback)


cdef class AutoBuffer:
    """ Event-driven I/O buffer
    """

    READ = Event.Read
    WRITE = Event.Write
    ERROR = Event.Error

    cdef PyAutoBuffer* c_buff

    def __cinit__(self, EventLoop loop, int fd, size_t block_size = 0, size_t buffer_size = 0):
        self.c_buff = new PyAutoBuffer(loop.c_loop, fd, block_size, buffer_size)

    def __dealloc__(self):
        del self.c_buff

    @property
    def active(self):
        """ Returns `True` if this is active (not closed). """
        return self.c_buff.active()

    @property
    def last_errno(self):
        """ Return last errno """
        return self.c_buff.lastErrno()

    @property
    def block_size(self):
        """ Size of block of data reads/writes to the I/O device at once. """
        return self.c_buff.blockSize()

    @property
    def buffer_size(self):
        """ Maximum size of the read/write buffers. """
        return self.c_buff.bufferSize()

    @property
    def incoming_size(self):
        """ Incomming buffer size. """
        return self.c_buff.incomingSize()

    @property
    def outcoming_size(self):
        """ Outcomming buffer size. """
        return self.c_buff.outcomingSize()

    def setup_read_until(self, callback, bytes delimiter, size_t max_bytes):
        """ Sets up buffer to reading until delimiter. """
        return self.c_buff.setup(<PyObject*>callback, <PyObject*>delimiter, max_bytes)

    def setup_read_exactly(self, callback, size_t num_bytes):
        """ Sets up buffer to reading exactly number of bytes. """
        tmp = b""
        return self.c_buff.setup(<PyObject*>callback, <PyObject*>tmp, num_bytes)

    def setup_flush(self, callback):
        """ Sets up buffer to flush outgoing buffer. """
        tmp = b""
        return self.c_buff.setup(<PyObject*>callback, <PyObject*>tmp, 0)

    def cancel_task(self):
        """ Cancels previous started task. """
        return self.c_buff.cancel()

    def read(self, int max_bytes):
        """ Read bytes from incoming buffer how much is there, but not more max_bytes. """
        return self.c_buff.read(max_bytes)

    def write(self, data):
        """ Writes data to the outcoming buffer.
        Returns number of bytes what has been written.
        """
        return self.c_buff.write(<PyObject*>data)

    def cleanup(self):
        """ Stops and cleanups buffer.
        """
        return self.c_buff.cleanup()
