#ifndef PY_SQUALL_DISPATCHER_HXX
#define PY_SQUALL_DISPATCHER_HXX

#include <boost/python.hpp>
#include <squall/Dispatcher.hxx>


namespace sq {

using std::placeholders::_1;
using std::placeholders::_2;
using std::placeholders::_3;

namespace bp = boost::python;

/* Specialized event dispatcher. */
class Dispatcher : squall::Dispatcher<PyObject> {

    PyObject *exc_type, *exc_value, *exc_traceback;

    bool on_event(const PyObject &target, int revents, const void *payload) {
        try {
            auto callable = const_cast<PyObject *>(&target);
            auto py_payload = (payload != nullptr) ? bp::object(*((int *)payload)) : bp::object();
            return bp::call<bool>(callable, revents, py_payload);
        } catch (...) {
            PyErr_Fetch(&exc_type, &exc_value, &exc_traceback);
            stop();
        }
        return false;
    }

    void on_apply(const PyObject &target) {
        try {
            bp::incref(const_cast<PyObject *>(&target));
        } catch (...) {
            PyErr_Fetch(&exc_type, &exc_value, &exc_traceback);
            stop();
        }
    }

    void on_free(const PyObject &target) {
        try {
            bp::decref(const_cast<PyObject *>(&target));
        } catch (...) {
            PyErr_Fetch(&exc_type, &exc_value, &exc_traceback);
            stop();
        }
    }

  public:
    Dispatcher()
        : squall::Dispatcher<PyObject>(ev::default_loop(), std::bind(&Dispatcher::on_event, this, _1, _2, _3),
                                       std::bind(&Dispatcher::on_apply, this, _1),
                                       std::bind(&Dispatcher::on_free, this, _1)),
          exc_type(nullptr), exc_value(nullptr), exc_traceback(nullptr) {}

    static Dispatcher &current() {
        static Dispatcher instance;
        return instance;
    }

    void start() {
        exc_type = exc_value = exc_traceback = nullptr;
        squall::Dispatcher<PyObject>::start();
        squall::Dispatcher<PyObject>::cleanup();
        if (exc_type != nullptr) {
            PyErr_Restore(exc_type, exc_value, exc_traceback);
            throw bp::error_already_set();
        }
    }

    void stop() {
        squall::Dispatcher<PyObject>::stop();
    }

    bool watch_timer(PyObject *target, double timeout) {
        return squall::Dispatcher<PyObject>::watch_timer(*target, timeout);
    }

    bool watch_io(PyObject *target, int fd, int events) {
        return squall::Dispatcher<PyObject>::watch_io(*target, fd, events);
    }

    bool watch_signal(PyObject *target, int signum) {
        return squall::Dispatcher<PyObject>::watch_signal(*target, signum);
    }

    bool disable_watching(PyObject *target) {
        return squall::Dispatcher<PyObject>::disable_watching(*target);
    }

    bool release_watching(PyObject *target) {
        return squall::Dispatcher<PyObject>::release_watching(*target);
    }
};

}
#endif
