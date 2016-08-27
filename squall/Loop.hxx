#ifndef SQUALL_LOOP_HXX
#define SQUALL_LOOP_HXX

#include <ev.h>


namespace squall {

/* Event loop */
class Loop {
    struct ev_loop *m_ptr;

  protected:
    /* Protected constructor. */
    Loop(struct ev_loop *ptr = nullptr) {
        if (ptr == nullptr)
            m_ptr = ev_default_loop(EVFLAG_AUTO);
        else
            m_ptr = ptr;
    }

  public:
    enum class Run : int { Default = 0, NoWait = EVRUN_NOWAIT, Once = EVRUN_ONCE };
    enum class Break : int { Cancel = EVBREAK_CANCEL, One = EVBREAK_ONE, All = EVBREAK_ALL };

    /* Returns default event loop. */
    static Loop &current() {
        static Loop instance;
        return instance;
    }

    /* Copy constructor. */
    Loop(const Loop &loop) : m_ptr(loop.m_ptr) {}

    /* Destructor. */
    ~Loop() {
        if (ev_is_default_loop(m_ptr))
            ev_loop_destroy(m_ptr);
    }

    /* Starts event loop. */
    bool start(Run flags = Run::Default) noexcept {
        return ev_run(m_ptr, static_cast<int>(flags));
    }

    /* Stops event loop. */
    void stop(Break how = Break::One) noexcept {
        ev_break(m_ptr, static_cast<int>(how));
    }

    struct ev_loop *ptr() const noexcept {
    	return m_ptr;
    }
};

} // end of squall
#endif