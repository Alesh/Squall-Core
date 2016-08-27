#include <boost/python.hpp>

#include "Dispatcher.hxx"
// #include "StreamAutoBuffer.hxx"

using namespace boost::python;
using namespace boost;
using namespace sq;


BOOST_PYTHON_MODULE(_squall) {

    class_<Dispatcher, noncopyable>("Dispatcher", "Event dispatcher")
        .add_static_property("READ", make_getter(int(squall::READ)))
        .add_static_property("WRITE", make_getter(int(squall::WRITE)))
        .add_static_property("TIMER", make_getter(int(squall::TIMER)))
        .add_static_property("SIGNAL", make_getter(int(squall::SIGNAL)))
        .add_static_property("CLEANUP", make_getter(int(squall::CLEANUP)))
        .add_static_property("ERROR", make_getter(int(squall::ERROR)))
        .def("current", &Dispatcher::current, return_value_policy<reference_existing_object>())
        .staticmethod("current")
        .def("start", &Dispatcher::start, "Starts the event dispatching.")
        .def("watch_timer", &Dispatcher::watch_timer, "Sets up the timer watching for a given target.")
        .def("watch_io", &Dispatcher::watch_io, "Sets up the I/O ready watching for a given target.")
        .def("watch_signal", &Dispatcher::watch_signal, "Sets up the system signal watching for a given target.")
        .def("disable_watching", &Dispatcher::disable_watching, "Deactivates all watchers for a given target")
        .def("release_watching", &Dispatcher::release_watching,
             "Deactivates and releases all watchers for a given target")
        .def("stop", &Dispatcher::stop, "Stop an event dispatching.");

    // class_<StreamAutoBuffer, noncopyable>("StreamAutoBuffer", init<bp::object, int, int, optional<bp::object>>())
    //     .add_property("max_size", &StreamAutoBuffer::get_max_size)
    //     .add_property("chunk_size", &StreamAutoBuffer::get_chunk_size)
    //     .add_property("outfilling", &StreamAutoBuffer::outfilling);
}
