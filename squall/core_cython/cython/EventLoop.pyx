import signal
import logging
from libcpp cimport bool
from cpython.ref cimport PyObject

cdef extern from "common/EventLoop.hxx":
    cdef cppclass CEventLoop "EventLoop":
        EventLoop() except +
        bool is_running()
        void start()
        void stop()
        bool setup_io(PyObject* callback, int fd, int mode)
        bool setup_timer(PyObject* callback, double seconds)
        bool setup_signal(PyObject* callback, int signum)
        bool update_io(PyObject* callback, int events)
        bool cancel_io(PyObject* callback)
        bool cancel_timer(PyObject* callback)
        bool cancel_signal(PyObject* callback)

    cdef enum Event:
        Read, Write, Timeout, Signal, Error


cdef class EventLoop:
    READ = Event.Read
    WRITE = Event.Write
    TIMEOUT = Event.Timeout
    SIGNAL = Event.Signal
    ERROR = Event.Error

    cdef CEventLoop* c_loop

    def __cinit__(self):
        self.c_loop = new CEventLoop()

    def __dealloc__(self):
        del self.c_loop

    def is_running(self):
        """ Returns `True` if tis is active.
        """
        return self.c_loop.is_running()

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

    def setup_timer(self, callback, double seconds):
        """ Setup to run the `callback` after a given `seconds` elapsed.
        Returns handle for using with `EventLoop.cancel_timer`
        """        
        if self.c_loop.setup_timer(<PyObject*>callback, seconds):
            return callback
        return None

    def setup_signal(self, callback, int signum):
        """ Setup to run the `callback` when system signal with a given `signum` received.
        Returns handle for using with `EventLoop.cancel_signal`
        """
        if self.c_loop.setup_signal(<PyObject*>callback, signum):
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

    def cancel_timer(self, callback):
        """ Cancels callback which was setup with `EventLoop.setup_timer`.
        """    
        return self.c_loop.cancel_timer(<PyObject*>callback)

    def cancel_signal(self, callback):
        """ Cancels callback which was setup with `EventLoop.setup_signal`.
        """
        return self.c_loop.cancel_signal(<PyObject*>callback)
