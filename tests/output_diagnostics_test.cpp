#include <cassert>
#include <cstring>
#include <initializer_list>
#include "output_diagnostics.h"

int main() {
    OutputDiagnostics diag;
    uint8_t host[47]{}, out[47]{};
    host[0] = 3; host[2] = 64; host[9] = 128; host[38] = 4;
    diag.received(host, 47);
    assert(diag.host[0] == 3 && diag.host[2] == 64 && diag.host[4] == 128 && diag.host[6] == 4);
    diag.received(host, 1);
    for (unsigned i = 1; i < 8; ++i) assert(diag.host[i] == 0);
    diag.accepted(host); assert(diag.valid == 3);
    diag.reset(); assert(diag.valid == 0);
    OutputTest test;
    std::memset(out, 0x55, 47);
    uint8_t original[47];std::memcpy(original, out, 47);
    test.apply(out, 0);assert(std::memcmp(out, original, 47) == 0);
    for (uint8_t kind = 1; kind <= 6; ++kind) {
        test.reset();test.start(kind, 0xfffffff0);
        std::memcpy(out, original, 47);
        test.apply(out, 0xfffffff0);
        assert(test.pending());
        assert(out[2] == (kind == 2 || kind == 3 ? 64 : 0));
        assert(out[3] == (kind == 1 || kind == 3 ? 64 : 0));
        assert(out[10] == (kind == 5 ? 0x21 : 5));
        assert(out[21] == (kind == 4 ? 0x21 : 5));
        for (unsigned i : {1u, 4u, 5u, 6u, 7u, 8u, 9u, 36u, 39u, 43u, 44u, 45u, 46u})
            assert(out[i] == original[i]); // no LED, volume, mute or power takeover
        test.apply(out, uint32_t(0xfffffff0 + 1999u));assert(test.kind == kind);
        test.apply(out, uint32_t(0xfffffff0 + 2000u));assert(!test.kind && test.release);
        assert((out[0] & 15) == 13 && !out[2] && !out[3] && !(out[38] & 4));
        uint8_t stale[47]{};test.accepted(stale);assert(test.release);
        test.accepted(out);assert(!test.pending());
        std::memcpy(out, original, 47);test.apply(out, 3000);
        assert(std::memcmp(out, original, 47) == 0);
    }
    test.start(3, 0);test.start(0, 10);test.apply(out, 10);
    assert(test.release && !out[2] && !out[3]);test.reset();assert(!test.pending());
}
