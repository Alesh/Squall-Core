/* Python extension module */
#include <Python.h>
#include <Squall.hxx>
#include <memory>

using Dispatcher = squall::Dispatcher<PyObject>;

static PyObject *type, *value, *traceback;
static std::unique_ptr<Dispatcher> dispatcher;

static inline void reset_exc_info() {
  type = nullptr;
  value = nullptr;
  traceback = nullptr;
}

static inline void on_apply(const PyObject &target) { Py_XINCREF(&target); }

static inline void on_release(const PyObject &target) { Py_XDECREF(&target); }

static bool on_event(const PyObject &target, int revents, const void *payload) {
  bool result = false;
  PyObject *pyresult;
  PyObject *arglist;

  if (payload != nullptr) {
    arglist = Py_BuildValue("(ii)", revents, *((int *)payload));
  } else {
    arglist = Py_BuildValue("(iO)", revents, Py_None);
  }

  pyresult = PyObject_CallObject(const_cast<PyObject *>(&target), arglist);
  if (pyresult != nullptr)
    result = PyObject_IsTrue(pyresult);
  else {
    PyErr_Fetch(&type, &value, &traceback);
    dispatcher->stop();
  }
  Py_XDECREF(pyresult);
  Py_XDECREF(arglist);
  return result;
}

extern "C" PyObject *pyStart(PyObject *self, PyObject *args) {
  reset_exc_info();
  dispatcher->start();
  dispatcher->cleanup();
  if (type != nullptr)
    PyErr_Restore(type, value, traceback);
  if (PyErr_Occurred() != nullptr)
    return nullptr;
  Py_RETURN_NONE;
}

extern "C" PyObject *pyStop(PyObject *self, PyObject *args) {
  dispatcher->stop();
  Py_RETURN_NONE;
}

extern "C" PyObject *pySetupWait(PyObject *self, PyObject *args) {
  double timeout;
  PyObject *target = nullptr;
  if (PyArg_ParseTuple(args, "Od", &target, &timeout)) {
    if (PyCallable_Check(target)) {
      if (!dispatcher->watch_timer(timeout, *target))
        PyErr_SetString(PyExc_RuntimeError, "Cannot setup watching");
    } else
      PyErr_SetString(PyExc_TypeError, "Event target must be callable");
  }
  if (PyErr_Occurred() != nullptr)
    return nullptr;
  Py_RETURN_NONE;
}

extern "C" PyObject *pySetupWaitIO(PyObject *self, PyObject *args) {
  int fd, events;
  PyObject *target = nullptr;
  if (PyArg_ParseTuple(args, "Oii", &target, &fd, &events)) {
    if (PyCallable_Check(target)) {
      if (!dispatcher->watch_io(fd, events, *target))
        PyErr_SetString(PyExc_RuntimeError, "Cannot setup watching");
    } else
      PyErr_SetString(PyExc_TypeError, "Event target must be callable");
  }
  if (PyErr_Occurred() != nullptr)
    return nullptr;
  Py_RETURN_NONE;
}

extern "C" PyObject *pySetupWaitSignal(PyObject *self, PyObject *args) {
  int signum;
  PyObject *target = nullptr;

  if (PyArg_ParseTuple(args, "Oi", &target, &signum)) {
    if (PyCallable_Check(target)) {
      if (!dispatcher->watch_signal(signum, *target))
        PyErr_SetString(PyExc_RuntimeError, "Cannot setup watching");
    } else
      PyErr_SetString(PyExc_TypeError, "Event target must be callable");
  }
  if (PyErr_Occurred() != nullptr)
    return nullptr;
  Py_RETURN_NONE;
}

extern "C" PyObject *pyDisableWatching(PyObject *self, PyObject *args) {
  bool result = false;
  PyObject *target = nullptr;
  if (PyArg_ParseTuple(args, "O", &target)) {
    result = (dispatcher->disable_watching(*target) == 0);
  }
  if (PyErr_Occurred() != nullptr)
    return nullptr;
  if (result)
    Py_RETURN_TRUE;
  Py_RETURN_FALSE;
}

extern "C" PyObject *pyReleaseWatching(PyObject *self, PyObject *args) {
  bool result = false;
  PyObject *target = nullptr;
  if (PyArg_ParseTuple(args, "O", &target)) {
    result = (dispatcher->release_watching(*target) == 0);
  }
  if (PyErr_Occurred() != nullptr)
    return nullptr;
  if (result)
    Py_RETURN_TRUE;
  Py_RETURN_FALSE;
}

PyMODINIT_FUNC PyInit__squall(void) {
  PyObject *module = nullptr;

  static PyMethodDef method_def[] = {
      {"start", pyStart, METH_VARARGS, "Starts event dispatching."},
      {"stop", pyStop, METH_VARARGS, "Stops event dispatching."},
      {"setup_wait", pySetupWait, METH_VARARGS, "Sets up timeout watching."},
      {"setup_wait_io", pySetupWaitIO, METH_VARARGS,
       "Sets up I/O event watching."},
      {"setup_wait_signal", pySetupWaitSignal, METH_VARARGS,
       "Sets up systen watching."},
      {"disable_watching", pyDisableWatching, METH_VARARGS,
       "Disables all associated watching for given event target."},
      {"release_watching", pyReleaseWatching, METH_VARARGS,
       "Releases given event target and all associated watching."},
      {nullptr, nullptr, 0, nullptr}};

  static struct PyModuleDef module_def = {PyModuleDef_HEAD_INIT, "_squall",
                                          "Native squall dispatcher", -1,
                                          method_def};
  module = PyModule_Create(&module_def);
  while (module != nullptr) {
    if (PyModule_AddIntConstant(module, "READ", squall::READ) != 0)
      break;
    if (PyModule_AddIntConstant(module, "WRITE", squall::WRITE) != 0)
      break;
    if (PyModule_AddIntConstant(module, "ERROR", squall::ERROR) != 0)
      break;
    if (PyModule_AddIntConstant(module, "SIGNAL", squall::SIGNAL) != 0)
      break;
    if (PyModule_AddIntConstant(module, "TIMEOUT", squall::TIMEOUT) != 0)
      break;
    if (PyModule_AddIntConstant(module, "CLEANUP", squall::CLEANUP) != 0)
      break;

    dispatcher = std::unique_ptr<Dispatcher>(
        new Dispatcher(ev::default_loop(), on_event, on_apply, on_release));
    return module;
  }

  Py_XDECREF(module);
  return nullptr;
}
