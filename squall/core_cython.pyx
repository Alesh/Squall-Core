""" Module of callback classes based on cython/libev
"""
import signal
import logging

cdef extern from "ev.h":
    struct ev_loop:
        pass

    ev_loop* ev_loop_new(unsigned int)
    int ev_run(ev_loop*, int)
    void ev_break(ev_loop*, int)
    void ev_loop_destroy(ev_loop*)

    struct ev_timer:
        int active;
        void *data
    ctypedef void (*cb_timer)(ev_loop*, ev_timer*, int)

    void ev_timer_init(ev_timer*, cb_timer, double, double);
    void ev_timer_set(ev_timer*, double, double)
    void ev_timer_start(ev_loop*, ev_timer*)
    void ev_timer_stop(ev_loop*, ev_timer*)

    struct ev_signal:
        int active;
        void *data
    ctypedef void (*cb_signal)(ev_loop*, ev_signal*, int)

    void ev_signal_init(ev_signal*, cb_signal, int);
    void ev_signal_set(ev_signal*, int)
    void ev_signal_start(ev_loop*, ev_signal*)
    void ev_signal_stop(ev_loop*, ev_signal*)

    struct ev_io:
        int active;
        void *data
        int fd
        int events
    ctypedef void (*cb_ready)(ev_loop*, ev_io*, int)

    void ev_io_init(ev_io*, cb_ready, int, int);
    void ev_io_set(ev_io*, int, int)
    void ev_io_start(ev_loop*, ev_io*)
    void ev_io_stop(ev_loop*, ev_io*)

    int EV_READ
    int EV_WRITE

    int EVRUN_ONCE
    int EVBREAK_ONE


cdef void ready_cb(ev_loop* p_loop, ev_io* p_watcher, int revents):
    ready_watcher = <ReadyHandle>p_watcher.data
    ready_watcher.trigger(revents)

cdef class ReadyHandle:
    cdef ev_io _watcher
    cdef object _callback

    def __cinit__(self):
        ev_io_init(&self._watcher, &ready_cb, 0, 0)
        self._watcher.data = <void*>self

    def __init__(self, callback, int fd, int events ):
        self._callback = callback
        ev_io_set(&self._watcher, fd, events)

    cdef start(self, ev_loop* p_loop):
        if self._watcher.active == 0:
            ev_io_start(p_loop, &self._watcher)
        return self._watcher.active != 0

    cdef update(self, ev_loop* p_loop, int events):
        if self._watcher.active != 0:
            ev_io_stop(p_loop, &self._watcher)
            ev_io_set(&self._watcher, self._watcher.fd, events)
            ev_io_start(p_loop, &self._watcher)
        return self._watcher.active != 0


    cdef stop(self, ev_loop* p_loop):
        if self._watcher.active != 0:
            ev_io_stop(p_loop, &self._watcher)

    cdef trigger(self, int revents):
        self._callback(revents)


cdef void timeout_cb(ev_loop* p_loop, ev_timer* p_watcher, int revents):
    timeout_watcher = <TimeoutHandle>p_watcher.data
    timeout_watcher.trigger(revents)

cdef class TimeoutHandle:
    cdef ev_timer _watcher
    cdef object _callback
    cdef object _result

    def __cinit__(self):
        ev_timer_init(&self._watcher, &timeout_cb, 0, 0)
        self._watcher.data = <void*>self

    def __init__(self, callback, double seconds, result):
        self._result = result
        self._callback = callback
        ev_timer_set(&self._watcher, seconds, seconds)

    cdef start(self, ev_loop* p_loop):
        if self._watcher.active == 0:
            ev_timer_start(p_loop, &self._watcher)
        return self._watcher.active != 0

    cdef stop(self, ev_loop* p_loop):
        if self._watcher.active != 0:
            ev_timer_stop(p_loop, &self._watcher)

    cdef trigger(self, int revents):
        self._callback(self._result)


cdef void signal_cb(ev_loop* p_loop, ev_signal* p_watcher, int revents):
    signal_watcher = <SignalHandle>p_watcher.data
    signal_watcher.trigger(revents)

cdef class SignalHandle:
    cdef ev_signal _watcher
    cdef object _callback

    def __cinit__(self):
        ev_signal_init(&self._watcher, &signal_cb, 0)
        self._watcher.data = <void*>self

    def __init__(self, callback, int signum):
        self._callback = callback
        ev_signal_set(&self._watcher, signum)

    cdef start(self, ev_loop* p_loop):
        if self._watcher.active == 0:
            ev_signal_start(p_loop, &self._watcher)
        return self._watcher.active != 0

    cdef stop(self, ev_loop* p_loop):
        if self._watcher.active != 0:
            ev_signal_stop(p_loop, &self._watcher)

    cdef trigger(self, int revents):
        self._callback(True)


cdef class EventLoop:
    """ libev/cython based implementation of `squall.core_.abc.EventLoop`
    """
    READ = EV_READ
    WRITE = EV_WRITE

    cdef ev_loop* _p_loop
    cdef int _running
    cdef set _readies
    cdef set _timeouts
    cdef set _signals

    def __cinit__(self):
        self._running = 0
        self._readies = set()
        self._timeouts = set()
        self._signals = set()
        self._p_loop = ev_loop_new(0)

    def __dealloc__(self):
        if self._p_loop is not NULL:
            ev_loop_destroy(self._p_loop)

    cpdef _on_sigint(self, int revents):
        self.stop()

    cpdef start(self):
        logging.info("Using cython/libev based callback classes")
        self.setup_signal(self._on_sigint, signal.SIGINT)
        try:
            self._running = 1
            while self._running != 0:
                ev_run(self._p_loop, EVRUN_ONCE)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = 0
            for handler in tuple(self._readies):
                self.cancel_io(handler)
            for handler in tuple(self._timeouts):
                self.cancel_timer(handler)
            for handler in tuple(self._signals):
                self.cancel_signal(handler)

    cpdef stop(self):
        if self._running != 0:
            self._running = 0
            ev_break(self._p_loop, EVBREAK_ONE)

    cpdef setup_io(self, callback, int fd, int events):
        ready_handle = ReadyHandle(callback, fd, events)
        if ready_handle.start(self._p_loop):
            self._readies.add(ready_handle)
            return ready_handle

    cpdef update_io(self, ReadyHandle ready_handle, int events):
        if ready_handle in self._readies:
            return ready_handle.update(self._p_loop, events)
        return False

    cpdef cancel_io(self, ReadyHandle ready_handle):
        if ready_handle in self._readies:
            ready_handle.stop(self._p_loop)
            self._readies.remove(ready_handle)
            return True
        return False

    cpdef setup_timer(self, callback, double seconds):
        timeout_handle = TimeoutHandle(callback, seconds, True)
        if timeout_handle.start(self._p_loop):
            self._timeouts.add(timeout_handle)
            return timeout_handle

    cpdef cancel_timer(self, TimeoutHandle timeout_handle):
        if timeout_handle in self._timeouts:
            timeout_handle.stop(self._p_loop)
            self._timeouts.remove(timeout_handle)
            return True
        return False

    cpdef setup_signal(self, callback, int signum):
        signal_handle = SignalHandle(callback, signum)
        if signal_handle.start(self._p_loop):
            self._signals.add(signal_handle)
            return signal_handle

    cpdef cancel_signal(self, SignalHandle signal_handle):
        if signal_handle in self._signals:
            signal_handle.stop(self._p_loop)
            self._signals.remove(signal_handle)
            return True
        return False
