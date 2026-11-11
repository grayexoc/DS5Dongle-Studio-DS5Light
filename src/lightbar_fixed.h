#ifndef STUDIO_LIGHTBAR_FIXED_H
#define STUDIO_LIGHTBAR_FIXED_H

#include <cstdint>

// No timer, allocation or I/O. Only a changed policy needs an idle report.
// A policy is acknowledged only after successful L2CAP submission.
class LightbarFixed {
    struct Key {
        uint8_t mode, r, g, b;
        bool operator==(const Key &v) const {
            return mode == v.mode && r == v.r && g == v.g && b == v.b;
        }
    };
    Key queued_{};
    bool valid_ = false;
    bool setup_pending_ = true;
    bool restore_pending_ = false;
    bool restore_prepared_ = false;
    uint8_t restore_r_ = 0, restore_g_ = 0, restore_b_ = 0;
    bool host_release_ = false, host_setup_pending_ = false;
    uint8_t host_setup_ = 0;
    bool host_color_valid_ = false;
    bool sent_color_valid_ = false;
    uint8_t sent_r_ = 0, sent_g_ = 0, sent_b_ = 0;
    static Key key(bool off, bool fixed, uint8_t r, uint8_t g, uint8_t b) {
        if (off) return {1, 0, 0, 0};
        if (fixed) return {2, r, g, b};
        return {0, 0, 0, 0};
    }
public:
    void reset() {
        valid_ = false; setup_pending_ = true; restore_pending_ = false;
        restore_prepared_ = false; host_release_ = host_setup_pending_ = false;
        host_color_valid_ = sent_color_valid_ = false;
    }
    // Only original host reports enter here; synthesis must not replay one-shot commands.
    void host_update(const uint8_t *data, uint8_t size) {
        if (size > 1 && (data[1] & 8)) { host_release_ = true; restore_prepared_ = false; }
        if (size > 41 && (data[38] & 2)) {
            host_setup_pending_ = true; host_setup_ = data[41]; restore_prepared_ = false;
            if (data[41] == 2) host_color_valid_ = true;
        }
        if (size > 46 && (data[1] & 4)) {
            host_color_valid_ = true;
            if (!sent_color_valid_ || data[44] != sent_r_ || data[45] != sent_g_ || data[46] != sent_b_)
                restore_pending_ = true;
            if (data[44] != restore_r_ || data[45] != restore_g_ || data[46] != restore_b_)
                restore_prepared_ = false;
        }
    }
    bool pending(bool off, bool fixed, uint8_t r, uint8_t g, uint8_t b) const {
        const Key next = key(off, fixed, r, g, b);
        return (setup_pending_ && (next.mode != 0 || host_color_valid_)) || (next.mode == 0 && (restore_pending_ || host_release_ || host_setup_pending_)) ||
               (!valid_ && next.mode != 0) || (valid_ && !(queued_ == next));
    }
    void apply(uint8_t *data, bool off, bool fixed, uint8_t r, uint8_t g, uint8_t b, bool temporary = false) {
        const Key next = key(off, fixed, r, g, b);
        data[1] &= ~0x08u;
        data[38] &= ~0x02u;
        data[41] = 0;
        // No host colour exists yet: preserve controller startup state, or release
        // a previous override instead of inventing black as the host colour.
        if (!next.mode && !host_color_valid_ && !temporary) {
            data[1] &= ~0x04u;
            if (restore_pending_ || (valid_ && queued_.mode) || host_release_) {
                data[1] = (data[1] & ~0x10u) | 8;
            }
            if (host_setup_pending_) { data[38] |= 2; data[41] = host_setup_; }
            restore_prepared_ = false;
            return;
        }
        if (setup_pending_) {
            // Take Bluetooth lightbar ownership only for a requested colour or override.
            data[38] |= 2; data[41] = 2;
            data[1] &= ~0x14u;
            data[38] &= ~1u;
            restore_prepared_ = false;
            return;
        }
        if (next.mode) {
            restore_pending_ = true;
            restore_prepared_ = false;
            // Block game resets/fades as well as RGB changes. Keep audio,
            // triggers and the separate player/mute LEDs untouched.
            data[1] = (data[1] & ~0x08u) | 0x04u;
            data[44] = next.r; data[45] = next.g; data[46] = next.b;
        } else if (host_release_ || host_setup_pending_) {
            // Reapply a host/user player pattern in the following report, after release.
            if (host_release_) data[1] = (data[1] & ~0x10u) | 8;
            if (host_setup_pending_) { data[38] |= 2; data[41] = host_setup_; }
        } else if (temporary) {
            restore_pending_ = true;
            restore_prepared_ = false;
        } else if (restore_pending_) {
            // Restore cached host RGB verbatim, including black/off; never invent a colour.
            data[1] |= 0x04u;
            data[38] &= ~0x02u;
            restore_prepared_ = true;
            restore_r_ = data[44]; restore_g_ = data[45]; restore_b_ = data[46];
        }
    }
    bool is_restore_report(const uint8_t *data) const {
        return restore_pending_ && restore_prepared_ && (data[1] & 0x04u) &&
               !(data[1] & 8) && !(data[38] & 0x02u) && data[44] == restore_r_ &&
               data[45] == restore_g_ && data[46] == restore_b_;
    }
    void accepted(const uint8_t *data, bool off, bool fixed, uint8_t r, uint8_t g, uint8_t b,
                  bool restore_report = false) {
        const Key next = key(off, fixed, r, g, b);
        if (!next.mode && !host_color_valid_) {
            if ((data[1] & 4) || ((data[38] & 2) && !host_setup_pending_)) {
                restore_pending_ = true;
                valid_ = false;
            }
            if ((data[1] & 8) && !(data[1] & 4)) {
                restore_pending_ = host_release_ = false;
                setup_pending_ = true;
                queued_ = next; valid_ = true;
            }
            if (host_setup_pending_ && (data[38] & 2) && data[41] == host_setup_)
                host_setup_pending_ = false;
            return;
        }
        if (data[1] & 4) {
            sent_color_valid_ = true;
            sent_r_ = data[44]; sent_g_ = data[45]; sent_b_ = data[46];
        }
        if (setup_pending_ && (data[38] & 2) && data[41] == 2) {
            setup_pending_ = false;
            restore_pending_ = true;
            valid_ = false;
            return; // Setup submission does not acknowledge RGB.
        }
        if (!next.mode && (host_release_ || host_setup_pending_)) {
            if (host_release_ && (data[1] & 8)) host_release_ = false;
            if (host_setup_pending_ && (data[38] & 2) && data[41] == host_setup_)
                host_setup_pending_ = false;
            return;
        }
        if ((data[38] & 2) || (data[1] & 8)) {
            // An older queued LED command can extinguish a newer colour.
            restore_pending_ = true; valid_ = false; return;
        }
        if (next.mode && (!(data[1] & 0x04) || data[44] != next.r ||
                          data[45] != next.g || data[46] != next.b)) {
            valid_ = false; // An older queued colour may have overtaken a slot change.
            return;
        }
        if (!next.mode && restore_pending_) {
            if (!restore_report || !is_restore_report(data)) return;
            restore_pending_ = false;
        }
        queued_ = next; valid_ = true;
    }
};

#endif
