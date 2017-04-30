#ifndef SQUALL__PY_AUTO_BUFFER__HXX
#define SQUALL__PY_AUTO_BUFFER__HXX

#include "PyEventLoop.hxx"
#include <Python.h>
#include <squall/EventBuffer.hxx>
#include <vector>

/* Event-driven I/O buffer implementation for python extension. */
class PyAutoBuffer : public squall::EventBuffer<PyObject*> {
    using Base = squall::EventBuffer<PyObject*>;

  public:
    /** Constructor */
    PyAutoBuffer(PyEventLoop* loop, int fd, size_t block_size = 0, size_t buffer_size = 0)
        : Base(*loop, fd, block_size, buffer_size) {}

    /**
     * Sets up a watching when buffer be ready to read
     * until found delimiter or reach a threshold.
     */
    int setup(PyObject* callback_, PyObject* delimiter_, size_t threshold = 0) {
        if (PyBytes_Check(delimiter_)) {
            char* p_data = PyBytes_AsString(delimiter_);
            std::vector<char> delimiter(p_data, p_data + PyBytes_Size(delimiter_));
            auto result = Base::setup(callback, delimiter, threshold);
            if (result != 0) {
                callback = callback_;
                Py_XINCREF(callback);
            }
            return result;
        }
        return 0;
    }

    /** Cancels a reading buffer task. */
    bool cancel() noexcept {
        if (Base::cancel()) {
            Py_XDECREF(callback);
            return true;
        }
        return false;
    }

    /**
     * Read bytes from incoming buffer how much is there, but not more `size`.
     * If `size == 0` tries to read bytes block defined with used threshold
     * and/or delimiter.
     */
    PyObject* read(size_t size = 0) {
        auto result = Base::read(size);
        return PyBytes_FromStringAndSize(result.data(), result.size());
    }

    /* Writes data to the outcoming buffer.
     * Returns number of bytes what has been written. */
    size_t write(PyObject* data_) {
        if (PyBytes_Check(data_)) {
            char* p_data = PyBytes_AsString(data_);
            std::vector<char> data(p_data, p_data + PyBytes_Size(data_));
            return Base::write(data);
        }
        return 0L;
    }

private:
    PyObject* callback;
};

#endif