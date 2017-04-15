#ifndef SQUALL__PYTHON__EVENT_LOOP__HXX
#define SQUALL__PYTHON__EVENT_LOOP__HXX

#include <Python.h>
#include <squall/base/EventLoop.hxx>

using squall::Event;
using namespace squall;
using namespace std::placeholders;

/* Event loop implementation for python extension. */
class EventLoop : base::EventLoop<PyObject*> {
    using Base = base::EventLoop<PyObject*>;

    PyThreadState* _thread_save;

    void _base_on_event(PyObject* callback, int revents) noexcept {
        PyEval_RestoreThread(_thread_save);
        PyObject* py_arglist = Py_BuildValue("(i)", revents);
        PyObject* py_result = PyObject_CallObject(callback, py_arglist);
        Py_XDECREF(py_arglist);
        Py_XDECREF(py_result);
        _thread_save = PyEval_SaveThread();
    }

  public:
    EventLoop()
        : Base(std::bind(&EventLoop::_base_on_event, this, _1, _2)) {}

    /* Return true if an event dispatching is active. */
    bool is_running() {
        return Base::is_running();
    }

    /* Starts event dispatching.*/
    void start() {
        _thread_save = PyEval_SaveThread();
        Base::start();
        PyEval_RestoreThread(_thread_save);
    }        

    /* Stops event dispatching.*/
    void stop() {
        Base::stop();
    }        

    /* Setup to call `callback` when the I/O device
     * with a given `fd` would be to read and/or write `mode`. */
    bool setup_io(PyObject* callback, int fd, int mode) {
        if (Base::setup_io(callback, fd, mode)) {
            Py_XINCREF(callback);
            return true;
        }
        return false;
    }

    /* Setup to call `callback` every `seconds`. */
    bool setup_timer(PyObject* callback, double seconds) {
        if (Base::setup_timer(callback, seconds)) {
            Py_XINCREF(callback);
            return true;
        }
        return false;
    }            

    /* Setup to call `callback` when the system signal
     * with a given `signum` recieved. */
    bool setup_signal(PyObject* callback, int signum) {
        if (Base::setup_signal(callback, signum)) {
            Py_XINCREF(callback);
            return true;
        }
        return false;
    }

    /* Updates I/O mode for event watchig extablished with method `setup_io`. */
    bool update_io(PyObject* callback, int mode) {
        return Base::update_io(callback, mode);
    }

    /* Cancels event watchig extablished with method `setup_io`. */
    bool cancel_io(PyObject* callback) {
        if (Base::cancel_io(callback)) {
            Py_XDECREF(callback);
            return true;
        }
        return false;
    }    

    /* Cancels event watchig extablished with method `setup_timer`. */
    bool cancel_timer(PyObject* callback) {
        if (Base::cancel_timer(callback)) {
            Py_XDECREF(callback);
            return true;
        }
        return false;
    }

    /* Cancels event watchig extablished with method `setup_signal`. */
    bool cancel_signal(PyObject* callback) {
        if (Base::cancel_signal(callback)) {
            Py_XDECREF(callback);
            return true;
        }
        return false;
    }

};

#endif