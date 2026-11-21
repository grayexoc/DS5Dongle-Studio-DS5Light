#pragma once
#include "output_diagnostics.h"

// Core-0 policy for an explicitly managed rear-control session. The caller
// supplies the current link epoch and verifies exclusive ownership on the host.
class RearRouteLease {
public:
    struct Token {
        uint32_t revision, link_epoch, generation;
    };

    static constexpr uint32_t pending_ms = 2000;
    static constexpr uint32_t active_ms = 1000;

    uint32_t arm(const Token &closed, uint32_t revision, uint32_t link_epoch,
             const UsbPlaybackObservation &usb, bool route_ready, uint32_t now) {
        advance(usb, now);
        if (state != State::Idle || !route_ready || !usb.known || usb.active || !usb.local_discard_complete ||
            closed.revision != revision || closed.link_epoch != link_epoch ||
            closed.generation != usb.generation) return 0;
        expected = {revision, link_epoch, uint32_t(usb.generation + 1)};
        invalidations = usb.invalidations;
        closed_count = usb.closes;
        if (++attempt == 0) ++attempt;
        last_refresh = now;
        state = State::Pending;
        return attempt;
    }

    // Commit comes from the host after exclusive Initialize succeeds. An
    // observed USB open alone never grants permission.
    bool commit(uint32_t request, const Token &opened, uint32_t revision, uint32_t link_epoch,
                const UsbPlaybackObservation &usb, bool route_ready, uint32_t now) {
        if (!matches(revision, link_epoch, usb, route_ready, now) || state != State::Pending || request != attempt ||
            !usb.active || opened.revision != expected.revision ||
            opened.link_epoch != expected.link_epoch || opened.generation != expected.generation)
            return false;
        sequence = 0;
        last_refresh = now;
        state = State::Active;
        return true;
    }

    bool renew(uint32_t request, uint32_t next_sequence, uint32_t revision, uint32_t link_epoch,
               const UsbPlaybackObservation &usb, bool route_ready, uint32_t now) {
        if (!permits(revision, link_epoch, usb, route_ready, now) ||
            request != attempt || next_sequence != uint32_t(sequence + 1)) return false;
        sequence = next_sequence;
        last_refresh = now;
        return true;
    }

    bool permits(uint32_t revision, uint32_t link_epoch,
                 const UsbPlaybackObservation &usb, bool route_ready, uint32_t now) {
        return matches(revision, link_epoch, usb, route_ready, now) && state == State::Active && usb.active;
    }

    enum class Rear { Legacy, Suppress, Control };

    Rear rear(uint32_t revision, uint32_t link_epoch, const UsbPlaybackObservation &usb,
              bool route_ready, uint32_t now) {
        if (permits(revision, link_epoch, usb, route_ready, now)) return Rear::Control;
        return state == State::Idle ? Rear::Legacy : Rear::Suppress;
    }

private:
    enum class State { Idle, Pending, Active, Blocked };

    void advance(const UsbPlaybackObservation &usb, uint32_t now) {
        if ((state == State::Pending || state == State::Active) &&
            uint32_t(now - last_refresh) >= (state == State::Pending ? pending_ms : active_ms))
            state = State::Blocked;
        if (state == State::Blocked && usb.known && !usb.active && usb.local_discard_complete &&
            (usb.closes != closed_count ||
             (usb.invalidations == invalidations && usb.generation == uint32_t(expected.generation - 1))))
            state = State::Idle;
    }

    // Call before consuming samples or releasing audio.
    bool matches(uint32_t revision, uint32_t link_epoch,
                 const UsbPlaybackObservation &usb, bool route_ready, uint32_t now) {
        advance(usb, now);
        if (state == State::Idle || state == State::Blocked) return false;
        if (!route_ready || revision != expected.revision || link_epoch != expected.link_epoch ||
            !usb.known || usb.invalidations != invalidations ||
            usb.generation != (usb.active ? expected.generation : uint32_t(expected.generation - 1))) {
            state = State::Blocked;
            advance(usb, now);
            return false;
        }
        return true;
    }

    Token expected{};
    uint32_t invalidations = 0, closed_count = 0, attempt = 0, last_refresh = 0, sequence = 0;
    State state = State::Idle;
};
