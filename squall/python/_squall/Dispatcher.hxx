#ifndef PY_SQUALL_DISPATCHER_HXX
#define PY_SQUALL_DISPATCHER_HXX

#include <boost/python.hpp>
#include <squall/Dispatcher.hxx>
#include <squall/Loop.hxx>

namespace bp = boost::python;


namespace squall {
namespace python {

using std::placeholders::_1;
using std::placeholders::_2;
using std::placeholders::_3;


/* Specialized event dispatcher. */
class Dispatcher : public squall::Dispatcher<PyObject> {

    bool m_active = false;
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

  protected:
    /* Protected constructor */
    Dispatcher(const Loop &loop = Loop::current())
        : squall::Dispatcher<PyObject>(std::bind(&Dispatcher::on_event, this, _1, _2, _3),
                                       std::bind(&Dispatcher::on_apply, this, _1),
                                       std::bind(&Dispatcher::on_free, this, _1), loop),
          exc_type(nullptr), exc_value(nullptr), exc_traceback(nullptr) {}


  public:
    /* Returns thread local event dispatcher instance. */
    static Dispatcher &current() {
        static Dispatcher instance;
        return instance;
    }

    void start() {
        exc_type = exc_value = exc_traceback = nullptr;
        m_active = true;
        Loop::current().start();
        m_active = false;
        squall::Dispatcher<PyObject>::cleanup();
        if (exc_type != nullptr) {
            PyErr_Restore(exc_type, exc_value, exc_traceback);
            throw bp::error_already_set();
        }
    }

    void stop() {
        Loop::current().stop();
    }

    void watch_timer(PyObject *target, double timeout) {
        if (!squall::Dispatcher<PyObject>::watch_timer(*target, timeout))
            throw std::runtime_error("Cannot setup timer watcher");
    }

    void watch_io(PyObject *target, int fd, int events) {
        if (!squall::Dispatcher<PyObject>::watch_io(*target, fd, events))
            throw std::runtime_error("Cannot setup I/O watcher");
    }

    void watch_signal(PyObject *target, int signum) {
        if (!squall::Dispatcher<PyObject>::watch_signal(*target, signum))
            throw std::runtime_error("Cannot setup signal watcher");
    }

    bool disable_watching(PyObject *target) {
        return squall::Dispatcher<PyObject>::disable_watching(*target);
    }

    bool release_watching(PyObject *target) {
        return squall::Dispatcher<PyObject>::release_watching(*target);
    }

    bool is_active() const {
        return (m_active && (!is_cleaning()));
    }
};
}
}
#endif
