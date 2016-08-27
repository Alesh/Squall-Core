#ifndef SQUALL_WATCHER_HXX
#define SQUALL_WATCHER_HXX

#include "Loop.hxx"
#include <ev.h>
#include <functional>


namespace squall {

using std::placeholders::_1;
using std::placeholders::_2;


/* Event codes */
enum Event : int {
    Read = EV_READ,
    Write = EV_WRITE,
    Timer = EV_TIMER,
    Signal = EV_SIGNAL,
    Error = EV_ERROR,
    Cleanup = EV_CLEANUP,
};


/* On event functor */
using OnEvent = std::function<void(int revents, const void *payload) noexcept>;


/* Abstract base watchers class */
class Watcher {
  public:
    virtual ~Watcher() {}

    /* Returns true if this watcher is active. */
    virtual bool is_active() const noexcept = 0;

    /* Starts event watching. */
    virtual bool start() noexcept = 0;

    /* Staps event watching. */
    virtual void stop() noexcept = 0;
};


template <typename W>
class GenericWatcher : public Watcher {
    OnEvent target;

  protected:
    W watcher = {};
    struct ev_loop *p_loop;

    static void callback(struct ev_loop *p_loop, W *p_watcher, int revents) {
        auto watcher = static_cast<GenericWatcher<W> *>(p_watcher->data);
        watcher->trigger(revents);
    }

    void trigger(int revent) noexcept {
        target(revent, nullptr);
    }

    void start_watching() noexcept;
    void stop_watching() noexcept;

  public:
    /* Constructor . */
    GenericWatcher<W>(const OnEvent &target, const Loop &loop) : target(target), p_loop(loop.ptr()) {
        watcher.cb = &GenericWatcher<W>::callback;
        watcher.data = static_cast<void *>(this);
    }

    /* Returns true if this watcher is active. */
    bool is_active() const noexcept {
        return watcher.active != 0;
    }

    /* Starts event watching. */
    bool start() noexcept {
        if (!is_active())
            start_watching();
        return is_active();
    }

    /* Stops event watching. */
    void stop() noexcept {
        if (is_active())
            stop_watching();
    }
};


template <>
inline void GenericWatcher<ev_cleanup>::start_watching() noexcept {
    ev_cleanup_start(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_cleanup>::stop_watching() noexcept {
    ev_cleanup_stop(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_timer>::start_watching() noexcept {
    ev_timer_start(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_timer>::stop_watching() noexcept {
    ev_timer_stop(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_io>::start_watching() noexcept {
    ev_io_start(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_io>::stop_watching() noexcept {
    ev_io_stop(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_signal>::start_watching() noexcept {
    ev_signal_start(p_loop, &watcher);
}

template <>
inline void GenericWatcher<ev_signal>::stop_watching() noexcept {
    ev_signal_stop(p_loop, &watcher);
}


using CleanupWatcher = GenericWatcher<ev_cleanup>;


/* Timer watcher */
class TimerWatcher : public GenericWatcher<ev_timer> {
  public:
    /* Constructor. */
    TimerWatcher(const OnEvent &target, const Loop &loop) : GenericWatcher<ev_timer>(target, loop) {}

    using Watcher::start;

    /* Starts timer watcher. */
    bool start(double after, double repeat = 0) noexcept {
        after = (after < 0) ? -1 : after;
        repeat = (repeat < 0) ? 0 : repeat;
        if (is_active())
            stop();
        ev_timer_set(&watcher, after, repeat);
        if (after >= 0)
            start_watching();
        return is_active();
    }
};

/* I/O Watcher */
class IoWatcher : public GenericWatcher<ev_io> {

    OnEvent target;

    void wrapped_target(int revents, const void *payload) noexcept {
        target(revents, &(watcher.fd));
    }

  public:
    /* Constructor. */
    IoWatcher(const OnEvent &target, const Loop &loop)
        : GenericWatcher<ev_io>(std::bind(&IoWatcher::wrapped_target, this, _1, _2), loop), target(target) {
        ev_io_set(&watcher, -1, 0);
    }


    /* Constructor with given fileno. */
    IoWatcher(const OnEvent &target, const Loop &loop, int fileno)
        : GenericWatcher<ev_io>(std::bind(&IoWatcher::wrapped_target, this, _1, _2), loop), target(target) {
        ev_io_set(&watcher, fileno, 0);
    }


    using Watcher::start;

    /* Returns fileno of watching device. */
    int fileno() const noexcept {
        return watcher.fd;
    }

    /* Starts I/O watcher with given event mask. */
    bool start(int revents) noexcept {
        return start(fileno(), revents);
    }

    /* Starts I/O watcher with given fileno and event mask. */
    bool start(int fileno, int revents) noexcept {
        fileno = (fileno < 0) ? -1 : fileno;
        revents = (revents < 0) ? 0 : revents;
        if (is_active())
            stop();
        ev_io_set(&watcher, fileno, revents);
        if ((fileno >= 0) && (revents > 0))
            start_watching();
        return is_active();
    }
};


/* Signal watcher */
class SignalWatcher : public GenericWatcher<ev_signal> {
    OnEvent target;

    void wrapped_target(int revents, const void *payload) noexcept {
        target(revents, &(watcher.signum));
    }

  public:
    /* Constructor. */
    SignalWatcher(const OnEvent &target, const Loop &loop)
        : GenericWatcher<ev_signal>(std::bind(&SignalWatcher::wrapped_target, this, _1, _2), loop), target(target) {
        ev_signal_set(&watcher, -1);
    }

    /* Constructor with given signal. */
    SignalWatcher(const OnEvent &target, const Loop &loop, int signum)
        : GenericWatcher<ev_signal>(std::bind(&SignalWatcher::wrapped_target, this, _1, _2), loop), target(target) {
        ev_signal_set(&watcher, signum);
    }

    using Watcher::start;

    /* Returns number of watching signal. */
    int signum() const noexcept {
        return watcher.signum;
    }


    /* Starts signal watcher. */
    bool start(int signum) noexcept {
        signum = (signum < 0) ? -1 : signum;
        if (is_active())
            stop();
        ev_signal_set(&watcher, signum);
        if (signum >= 0)
            start_watching();
        return is_active();
    }
};


} // end of squall
#endif