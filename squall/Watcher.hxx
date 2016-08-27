#ifndef SQUALL_WATCHER_HXX
#define SQUALL_WATCHER_HXX

#include <ev++.h>
#include <functional>

namespace squall {

enum : int {
    READ = EV_READ,
    WRITE = EV_WRITE,
    TIMER = EV_TIMER,
    SIGNAL = EV_SIGNAL,
    ERROR = EV_ERROR,
    CLEANUP = EV_CLEANUP,
};


/** On event functor */
using OnEvent = std::function<void(int revents, const void *) noexcept>;


/**
 * Abstract base watchers class
 */
class Watcher {
  public:
    virtual ~Watcher() {}

    /** Returns bitwise mask of possible events. */
    virtual int events() const = 0;

    /** Returns true if this watcher is active. */
    virtual bool is_active() const = 0;

    /** Starts event watching. */
    virtual void start_() = 0;

    /** Staps event watching. */
    virtual void stop() = 0;
};


/**
 * Generic watchers class.
 */
template <typename W>
class GenericWatcher : public Watcher, public W {
    OnEvent target;
    void trigger(W &w, int revents);

  public:
    /** Constructor for the default loop. */
    GenericWatcher<W>(OnEvent &target) : W(ev::default_loop()), target(target) {
        this->template set<GenericWatcher<W>, &GenericWatcher<W>::trigger>(this);
    }

    /** Constructor for the concrete loop. */
    GenericWatcher<W>(const ev::loop_ref &loop, OnEvent &target) : W(loop), target(target) {
        this->template set<GenericWatcher<W>, &GenericWatcher<W>::trigger>(this);
    }

    /** Returns bitwise mask of possible events. */
    int events() const;

    /** Returns true if this watcher is active. */
    bool is_active() const {
        return W::is_active();
    }

    /** Starts event watching. */
    void start_() {
        W::start();
    }

    /** Staps event watching. */
    void stop() {
        W::stop();
    }
};


using IoWatcher = GenericWatcher<ev::io>;

template <>
void IoWatcher::trigger(ev::io &w, int revents) {
    target(revents, &(w.fd));
}

template <>
inline int IoWatcher::events() const {
    return READ | WRITE | ERROR | CLEANUP;
}


using TimerWatcher = GenericWatcher<ev::timer>;

template <>
void TimerWatcher::trigger(ev::timer &w, int revents) {
    target(revents, nullptr);
}

template <>
inline int TimerWatcher::events() const {
    return TIMER | ERROR | CLEANUP;
}


using SignalWatcher = GenericWatcher<ev::sig>;

template <>
void SignalWatcher::trigger(ev::sig &w, int revents) {
    target(revents, &(w.signum));
}

template <>
inline int SignalWatcher::events() const {
    return SIGNAL | ERROR | CLEANUP;
}

} // end of squall
#endif