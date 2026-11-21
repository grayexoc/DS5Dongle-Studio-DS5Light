#include <cassert>
#include "rear_route_lease.h"

int main() {
    UsbPlaybackObservation usb;
    RearRouteLease lease;
    using Rear = RearRouteLease::Rear;
    assert(lease.rear(7, 2, usb, true, 0) == Rear::Legacy);
    usb.set_alternate(0);
    assert(!lease.arm({7, 2, usb.generation}, 7, 2, usb, true, 0));
    usb.mark_local_discard_complete();
    const RearRouteLease::Token closed{7, 2, usb.generation};
    assert(!lease.arm(closed, 8, 2, usb, true, 0));
    assert(!lease.arm(closed, 7, 3, usb, true, 0));
    assert(!lease.arm(closed, 7, 2, usb, false, 0));
    auto request = lease.arm(closed, 7, 2, usb, true, 0);
    assert(request);
    assert(!lease.arm(closed, 7, 2, usb, true, 0));
    assert(!lease.permits(7, 2, usb, true, 0));
    usb.set_alternate(1);
    assert(lease.rear(7, 2, usb, true, 0) == Rear::Suppress);
    assert(!lease.commit(request, closed, 7, 2, usb, true, 0));
    assert(!lease.commit(request, {8, 2, usb.generation}, 7, 2, usb, true, 0));
    assert(lease.commit(request, {7, 2, usb.generation}, 7, 2, usb, true, 0));
    assert(!lease.commit(request, {7, 2, usb.generation}, 7, 2, usb, true, 0));
    assert(lease.permits(7, 2, usb, true, 0));
    assert(!lease.permits(8, 2, usb, true, 0));
    assert(lease.rear(7, 2, usb, true, 0) == Rear::Suppress);
    usb.set_alternate(0);
    assert(lease.rear(8, 2, usb, true, 0) == Rear::Suppress);
    usb.mark_local_discard_complete();
    assert(lease.rear(8, 2, usb, true, 0) == Rear::Legacy);
    assert(!lease.arm(closed, 7, 2, usb, true, 0));
    request = lease.arm({8, 2, usb.generation}, 8, 2, usb, true, 0);
    assert(request);
    usb.set_alternate(1);
    assert(!lease.permits(8, 2, usb, true, 0));
    assert(lease.commit(request, {8, 2, usb.generation}, 8, 2, usb, true, 0));
    assert(lease.permits(8, 2, usb, true, 0));
    usb.set_alternate(1);
    assert(!lease.permits(8, 2, usb, true, 0));

    usb.generation = 0xfffffffe;
    usb.set_alternate(0);
    usb.mark_local_discard_complete();
    request = lease.arm({8, 2, usb.generation}, 8, 2, usb, true, 0);
    assert(request);
    usb.set_alternate(1);
    assert(!lease.permits(8, 2, usb, true, 0));
    assert(lease.commit(request, {8, 2, usb.generation}, 8, 2, usb, true, 0));
    assert(lease.permits(8, 2, usb, true, 0));
    assert(!lease.renew(request, 2, 8, 2, usb, true, 400));
    assert(lease.renew(request, 1, 8, 2, usb, true, 500));
    assert(!lease.renew(request, 1, 8, 2, usb, true, 1200));
    assert(lease.permits(8, 2, usb, true, 1499));
    assert(lease.rear(8, 2, usb, true, 1500) == Rear::Suppress);
    assert(!lease.renew(request, 2, 8, 2, usb, true, 1500));
    usb.invalidate();
    assert(lease.rear(8, 2, usb, true, 1501) == Rear::Suppress);
    assert(!lease.commit(request, {8, 2, 0}, 8, 2, usb, true, 1501));
    assert(!lease.permits(8, 2, usb, true, 0));

    usb.set_alternate(0);
    usb.mark_local_discard_complete();
    const RearRouteLease::Token retry{8, 2, usb.generation};
    const uint32_t start = 0xffffff00;
    const auto expired = lease.arm(retry, 8, 2, usb, true, start);
    assert(expired);
    request = lease.arm(retry, 8, 2, usb, true, uint32_t(start + RearRouteLease::pending_ms));
    assert(request && request != expired);
    usb.set_alternate(1);
    const RearRouteLease::Token opened{8, 2, usb.generation};
    assert(!lease.commit(expired, opened, 8, 2, usb, true, 2000));
    assert(!lease.permits(8, 2, usb, true, 2000));
    assert(lease.commit(request, opened, 8, 2, usb, true, 2000));
    assert(lease.permits(8, 2, usb, true, 2000));
}
