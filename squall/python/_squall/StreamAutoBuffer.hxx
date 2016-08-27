#ifndef PY_SQUALL_STREAM_AUTO_BUFFER_HXX
#define PY_SQUALL_STREAM_AUTO_BUFFER_HXX

#include <boost/python.hpp>
#include <squall/StreamAutoBuffer.hxx>

#include "Dispatcher.hxx"

namespace sq {

namespace bp = boost::python;


/* Specialized socket stream autobuffer. */
class StreamAutoBuffer : squall::StreamAutoBuffer<PyObject> {

  public:
    StreamAutoBuffer(const bp::object &socket, int chunk_size, int max_size)
        : squall::StreamAutoBuffer<PyObject>(bp::extract<int>(socket.attr("fileno")()), chunk_size, max_size,
                                             Dispatcher::current()) {}

    StreamAutoBuffer(const bp::object &socket, int chunk_size, int max_size, const bp::object &dispatcher)
        : squall::StreamAutoBuffer<PyObject>(bp::extract<int>(socket.attr("fileno")()), chunk_size, max_size,
                                             bp::extract<Dispatcher>(dispatcher)) {}

    int get_max_size() {
        return max_size;
    }

    int get_chunk_size() {
        return chunk_size;
    }

};
}
#endif
