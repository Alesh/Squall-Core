#ifndef SQUALL_DISPATCHER_HXX
#define SQUALL_DISPATCHER_HXX

#include <map>
#include <memory>
#include <vector>

#include "Watcher.hxx"

namespace squall {

using std::placeholders::_1;
using std::placeholders::_2;
using std::placeholders::_3;

template <typename T>
using OnTarget = std::function<void(const T &target) noexcept>;

template <typename T>
using OnTargetEvent = std::function<bool(const T &target, int revents, const void *payload) noexcept>;

using Watchers = std::vector<std::unique_ptr<Watcher>>;


/**
 * Generic event dispatcher.
 */
template <typename T>
class Dispatcher {

    bool running = false;
    std::map<const T *, Watchers> targets;

    ev::loop_ref loop;
    OnTargetEvent<T> on_target_event;
    OnTarget<T> on_target_apply;
    OnTarget<T> on_target_free;
    bool on_target_present;


    void handler(const T *target, int revents, const void *payload = nullptr) {
        disable_watching(*target);
        if (on_target_event(*target, revents, payload))
            enable_watching(*target);
    }


    template <typename W>
    W *setup_watching(OnEvent on_target_event, const T *target, std::function<Watcher *(Watcher *)> approve) {
        W *p_watcher = nullptr;
        auto found = targets.find(target);
        if (found == targets.end()) {
            found = targets.insert(found, std::make_pair(target, Watchers()));
            if (on_target_present)
                on_target_apply(*target);
        }
        for (const auto &up_watcher : found->second) {
            p_watcher = static_cast<W *>(approve(up_watcher.get()));
            if (p_watcher != nullptr) {
                p_watcher->stop();
                break;
            }
        }
        if (p_watcher == nullptr) {
            auto up_watcher = std::unique_ptr<Watcher>(new W(loop, on_target_event));
            p_watcher = static_cast<W *>(up_watcher.get());
            found->second.push_back(std::move(up_watcher));
        }
        return p_watcher;
    }

  public:
    /** Constructor with  "apply/release" handling for target. */
    Dispatcher(const ev::loop_ref &loop, const OnTargetEvent<T> &on_target_event, const OnTarget<T> &on_target_apply,
               const OnTarget<T> &on_target_free)
        : loop(loop), on_target_event(on_target_event), on_target_apply(on_target_apply),
          on_target_free(on_target_free), on_target_present(true) {}


    /** General constructor. */
    Dispatcher(const ev::loop_ref &loop, const OnTargetEvent<T> &on_target_event)
        : loop(loop), on_target_event(on_target_event), on_target_apply(nullptr), on_target_free(nullptr),
          on_target_present(false) {}


    /** Destructor */
    ~Dispatcher() {
        if (running)
            stop();
        cleanup();
    }


    /* Starts event dispatching. */
    void start() {
        running = true;
        loop.run(0);
        running = false;
    }


    /* Stops event dispatching. */
    void stop() {
        loop.break_loop();
    }


    /** Setups the watcher of timer for a target. */
    bool watch_timer(const T &target, double timeout) {
        auto on_event = std::bind(&Dispatcher::handler, this, &target, _1, _2);
        auto approve = [](Watcher *p_watcher) {
            if (p_watcher->events() & TIMER)
                return p_watcher;
            return static_cast<Watcher *>(nullptr);
        };
        if (auto p_watcher = setup_watching<TimerWatcher>(on_event, &target, approve)) {
            p_watcher->start(timeout, timeout);
            return p_watcher->is_active();
        }
        return false;
    }


    /* Setups the I/O ready watcher for a target. */
    bool watch_io(const T &target, int fd, int events) {
        auto on_event = std::bind(&Dispatcher::handler, this, &target, _1, _2);
        auto approve = [fd](Watcher *p_watcher) {
            if (p_watcher->events() & (READ | WRITE)) {
                if ((static_cast<IoWatcher *>(p_watcher)->fd) == fd)
                    return p_watcher;
            }
            return static_cast<Watcher *>(nullptr);
        };
        if (auto p_watcher = setup_watching<IoWatcher>(on_event, &target, approve)) {
            p_watcher->start(fd, events);
            return p_watcher->is_active();
        }
        return false;
    }


    /* Setups the system signal watcher for a target. */
    bool watch_signal(const T &target, int signum) {
        auto on_event = std::bind(&Dispatcher::handler, this, &target, _1, _2);
        auto approve = [signum](Watcher *p_watcher) {
            if (p_watcher->events() & SIGNAL) {
                if ((static_cast<SignalWatcher *>(p_watcher))->signum == signum)
                    return p_watcher;
            }
            return static_cast<Watcher *>(nullptr);
        };
        if (auto p_watcher = setup_watching<SignalWatcher>(on_event, &target, approve)) {
            p_watcher->start(signum);
            return p_watcher->is_active();
        }
        return false;
    }


    /** Activates all watchers for a target. */
    bool enable_watching(const T &target) {
        auto found = targets.find(&target);
        if (found != targets.end()) {
            for (const auto &up_watcher : found->second)
                if (!up_watcher->is_active())
                    up_watcher->start_();
            return true;
        }
        return false;
    }


    /** Deactivates all watchers for a target. */
    bool disable_watching(const T &target) {
        auto found = targets.find(&target);
        if (found != targets.end()) {
            for (const auto &up_watcher : found->second) {
                if (up_watcher->is_active())
                    up_watcher->stop();
            }
            return true;
        }
        return false;
    }


    /** Deactivates and releases all watchers for a target. */
    bool release_watching(const T &target) {
        auto found = targets.find(&target);
        if (found != targets.end()) {
            for (const auto &up_watcher : found->second) {
                if (up_watcher->is_active())
                    up_watcher->stop();
            }
            found->second.clear();
            targets.erase(&target);
            if (on_target_present)
                on_target_free(target);
            return true;
        }
        return false;
    }

    /** Cleanups (deactivates and releases) all targets. */
    void cleanup() {
        std::vector<const T *> all;
        all.reserve(targets.size());
        std::vector<const T *> active;
        active.reserve(targets.size());
        for (auto &target_pair : targets) {
            all.push_back(target_pair.first);
            for (const auto &up_watcher : target_pair.second) {
                if (up_watcher->is_active()) {
                    active.push_back(target_pair.first);
                    break;
                }
            }
        }
        for (auto &target : active)
            handler(target, CLEANUP);
        for (auto &target : all)
            release_watching(*target);
    }
};

} // end of squall
#endif
