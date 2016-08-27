#ifndef SQUALL_STREAM_AUTO_BUFFER_HXX
#define SQUALL_STREAM_AUTO_BUFFER_HXX

#include <vector>

#include "Dispatcher.hxx"


namespace squall {

emplate <typename T>
using OnResult = std::function<void(int revents, const std::vector<unsigned char> &bytes) noexcept>;


/**
 * Generic socket stream autobuffer.
 */
template <typename T>
class StreamAutoBuffer {

  protected:
    int fileno;
    int chunk_size;
    int max_size;
    const Dispatcher<T> &dispatcher;

  public:
    StreamAutoBuffer(int fileno, int chunk_size, int max_size, const Dispatcher<T> &dispatcher)
        : fileno(fileno), chunk_size(chunk_size), max_size(max_size), dispatcher(dispatcher) {}

    double outfilling() {
        return 0;
    }

    const std::vector<unsigned char> &read_bytes(size_t num_bytes) {}
    bool watch_read_bytes(size_t num_bytes, double timeout, const T &target) {}

};

} // end of squall
#endif