from libcpp cimport bool
from cpython.ref cimport PyObject


cdef extern from "PyEventLoop.hxx":
    cdef cppclass PyEventLoop:
        CxxEventLoop() except +
        bool running()
        void start()
        void stop()
        bool setup_io(PyObject* callback, int fd, int mode)
        bool update_io(PyObject* callback, int events)
        bool cancel_io(PyObject* callback)
        bool setup_timer(PyObject* callback, double seconds)
        bool update_timer(PyObject* callback, double seconds)
        bool cancel_timer(PyObject* callback)
        bool setup_signal(PyObject* callback, int signum)
        bool cancel_signal(PyObject* callback)

    cdef enum Event:
        Read "Event::Read",
        Write "Event::Write",
        Timeout "Event::Timeout",
        Signal "Event::Signal",
        Error "Event::Error",
        Cleanup "Event::Cleanup",
        Buffer "Event::Buffer",

cdef extern from "PyAutoBuffer.hxx":
    cdef cppclass PyAutoBuffer:
        PyAutoBuffer(PyEventLoop* loop, int fd, size_t block_size, size_t buffer_size) except +
        bool active()
        int lastErrno()
        size_t blockSize()
        size_t bufferSize()
        size_t incomingSize()
        size_t outcomingSize()
        int setup(PyObject* callback, PyObject* delimiter, size_t threshold)
        bool cancel()
        object read(size_t size)
        size_t write(PyObject* data)
        void cleanup()
