#ifndef SQUALL__PY_EVENT_LOOP__HXX
#define SQUALL__PY_EVENT_LOOP__HXX

#include <Python.h>
#include <squall/EventLoop.hxx>
#include <squall/Dispatcher.hxx>

using squall::Event;
using std::placeholders::_1;
using std::placeholders::_2;

/* Event loop implementation for python extension. */
class PyEventLoop : public squall::Dispatcher<PyObject*> {
    using Base = squall::Dispatcher<PyObject*>;

    PyThreadState* thread_save;

    void on_event(PyObject* callback, int revents) noexcept {
        if (revents == Event::Cleanup)
            return;
        PyEval_RestoreThread(thread_save);
        PyObject* py_arglist = Py_BuildValue("(i)", revents);
        PyObject* py_result = PyObject_CallObject(callback, py_arglist);
        Py_XDECREF(py_arglist);
        Py_XDECREF(py_result);
        thread_save = PyEval_SaveThread();
    }

  public:
    PyEventLoop() : Base(std::bind(&PyEventLoop::on_event, this, _1, _2), squall::EventLoop::create()) {}

    /* Return true if an event dispatching is active. */
    bool running() {
        return (Base::shared_loop()->running() && Base::active());
    }

    /* Starts event dispatching.*/
    void start() {
        thread_save = PyEval_SaveThread();
        Base::shared_loop()->start();
        PyEval_RestoreThread(thread_save);
    }

    /* Stops event dispatching.*/
    void stop() {
        Base::shared_loop()->stop();
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