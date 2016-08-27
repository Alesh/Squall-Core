#include <boost/python.hpp>

#include "Dispatcher.hxx"

using namespace boost;
using namespace boost::python;
using namespace squall::python;


BOOST_PYTHON_MODULE(_squall) {

    class_<Dispatcher, noncopyable>("Dispatcher", "Event dispatcher", no_init)
        .add_static_property("READ", make_getter(int(squall::Event::Read)))
        .add_static_property("WRITE", make_getter(int(squall::Event::Write)))
        .add_static_property("TIMER", make_getter(int(squall::Event::Timer)))
        .add_static_property("SIGNAL", make_getter(int(squall::Event::Signal)))
        .add_static_property("CLEANUP", make_getter(int(squall::Event::Cleanup)))
        .add_static_property("ERROR", make_getter(int(squall::Event::Error)))
        .def("current", &Dispatcher::current, return_value_policy<reference_existing_object>())
        .staticmethod("current")
        .add_property("active", &Dispatcher::is_active, "True if dispatching is active.")
        .def("start", &Dispatcher::start, "Starts the event dispatching.")
        .def("watch_timer", &Dispatcher::watch_timer, "Sets up the timer watching for a given target.")
        .def("watch_io", &Dispatcher::watch_io, "Sets up the I/O ready watching for a given target.")
        .def("watch_signal", &Dispatcher::watch_signal, "Sets up the system signal watching for a given target.")
        .def("disable_watching", &Dispatcher::disable_watching, "Deactivates all watchers for a given target")
        .def("release_watching", &Dispatcher::release_watching,
             "Deactivates and releases all watchers for a given target")
        .def("stop", &Dispatcher::stop, "Stop an event dispatching.");
}
