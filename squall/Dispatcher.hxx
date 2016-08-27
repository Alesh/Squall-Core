#ifndef SQUALL_DISPATCHER_HXX
#define SQUALL_DISPATCHER_HXX

#include "Loop.hxx"
#include "Watcher.hxx"
#include <map>
#include <memory>
#include <vector>


namespace squall {

using std::placeholders::_1;
using std::placeholders::_2;

template <typename T>
using OnTarget = std::function<void(const T &target) noexcept>;

template <typename T>
using OnTargetEvent = std::function<bool(const T &target, int revents, const void *payload) noexcept>;

using Watchers = std::vector<std::unique_ptr<Watcher>>;


/* Generic base dispatcher */
template <typename T>
class Dispatcher {

    bool m_cleaning = false;
    std::map<const T *, Watchers> targets;
    std::unique_ptr<CleanupWatcher> cleanup_watcher;

    OnTargetEvent<T> on_target_event;
    OnTarget<T> on_target_apply;
    OnTarget<T> on_target_free;
    bool on_target_present;
    Loop m_loop;

    void initialize() {
        cleanup_watcher = std::unique_ptr<CleanupWatcher>(
            new CleanupWatcher([this](int revents, const void *payload) { this->cleanup(); }, m_loop));
        cleanup_watcher->start();
    }

    void handler(const T *target, int revents, const void *payload = nullptr) {
        disable_watching(*target);
        if (on_target_event(*target, revents, payload))
            enable_watching(*target);
    }

  protected:
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
            if (p_watcher != nullptr)
                break;
        }
        if (p_watcher == nullptr) {
            auto up_watcher = std::unique_ptr<Watcher>(new W(on_target_event, m_loop));
            p_watcher = static_cast<W *>(up_watcher.get());
            found->second.push_back(std::move(up_watcher));
        }
        return p_watcher;
    }

  public:
    /* Returns true if dispatcher is cleaning. */
    bool is_cleaning() const {
        return m_cleaning;
    }

    /* Event loop. */
    const Loop &loop() const {
        return m_loop;
    }

    /* Constructor. */
    Dispatcher(const OnTargetEvent<T> &on_target_event, const Loop &loop)
        : on_target_event(on_target_event), on_target_apply(nullptr), on_target_free(nullptr), on_target_present(false),
          m_loop(loop) {
        initialize();
    }

    /* Constructor with  "apply/release" handling for target. */
    Dispatcher(const OnTargetEvent<T> &on_target_event, const OnTarget<T> &on_target_apply,
               const OnTarget<T> &on_target_free, const Loop &loop)
        : on_target_event(on_target_event), on_target_apply(on_target_apply), on_target_free(on_target_free),
          on_target_present(true), m_loop(loop) {
        initialize();
    }

    /* Destructor */
    virtual ~Dispatcher() {
        cleanup();
    }

    /* Setups the watcher of timer for a target. */
    bool watch_timer(const T &target, double timeout) {
        if (!m_cleaning) {
            auto on_event = std::bind(&Dispatcher::handler, this, &target, _1, _2);
            auto approve = [](Watcher *p_watcher) {
                if (dynamic_cast<TimerWatcher *>(p_watcher))
                    return p_watcher;
                return static_cast<Watcher *>(nullptr);
            };
            if (auto p_watcher = setup_watching<TimerWatcher>(on_event, &target, approve))
                return p_watcher->start(timeout, timeout);
        }
        return false;
    }

    /* Setups the I/O ready watcher for a target. */
    bool watch_io(const T &target, int fileno, int events) {
        if (!m_cleaning) {
            auto on_event = std::bind(&Dispatcher::handler, this, &target, _1, _2);
            auto approve = [&fileno](Watcher *p_watcher) {
                if (auto p_io_watcher = dynamic_cast<IoWatcher *>(p_watcher)) {
                    auto fileno_ = p_io_watcher->fileno();
                    if ((fileno_ == fileno) || (fileno_ == -1))
                        return p_watcher;
                }
                return static_cast<Watcher *>(nullptr);
            };
            if (auto p_watcher = setup_watching<IoWatcher>(on_event, &target, approve))
                return p_watcher->start(fileno, events);
        }
        return false;
    }

    /* Setups the system signal watcher for a target. */
    bool watch_signal(const T &target, int signum) {
        if (!m_cleaning) {
            auto on_event = std::bind(&Dispatcher::handler, this, &target, _1, _2);
            auto approve = [&signum](Watcher *p_watcher) {
                if (auto p_sig_watcher = dynamic_cast<SignalWatcher *>(p_watcher)) {
                    auto signum_ = p_sig_watcher->signum();
                    if ((signum_ == signum) || (signum_ == -1))
                        return p_watcher;
                }
                return static_cast<Watcher *>(nullptr);
            };
            if (auto p_watcher = setup_watching<SignalWatcher>(on_event, &target, approve))
                return p_watcher->start(signum);
        }
        return false;
    }

    /* Activates all watchers for a target. */
    bool enable_watching(const T &target) {
        if (!m_cleaning) {
            auto found = targets.find(&target);
            if (found != targets.end()) {
                for (const auto &up_watcher : found->second)
                    if (!up_watcher->is_active())
                        up_watcher->start();
                return true;
            }
        }
        return false;
    }

    /* Deactivates all watchers for a target. */
    bool disable_watching(const T &target) {
        auto found = targets.find(&target);
        if (found != targets.end()) {
            for (const auto &up_watcher : found->second)
                up_watcher->stop();
            return true;
        }
        return false;
    }

    /* Deactivates and releases all watchers for a target. */
    bool release_watching(const T &target) {
        auto found = targets.find(&target);
        if (found != targets.end()) {
            for (const auto &up_watcher : found->second)
                up_watcher->stop();
            found->second.clear();
            targets.erase(&target);
            if (on_target_present)
                on_target_free(target);
            return true;
        }
        return false;
    }

    /* Cleanups (deactivates and releases) all targets. */
    void cleanup() {
        m_cleaning = true;
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
            handler(target, Event::Cleanup);
        for (auto &target : all)
            release_watching(*target);
        m_cleaning = false;
    }
};


} // end of squall
#endif
