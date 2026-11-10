"""One-shot channel negotiation. A capture format is not a game-layout claim."""
from windows_audio import snapshot


def candidates(requested,hint=None):
    if requested not in (0,2,6,8):raise ValueError('Invalid capture channel setting')
    if requested:return (requested,)
    if hint in (1,2):return (2,)
    if hint==6:return (6,2)
    return (8,6,2)


def process_hint(pid):
    try:
        result=snapshot(channel_pid=pid)
        # Unreadable or incomplete enumeration is not positive detection.
        if result['complete']:
            return result['sessions'].get(pid,{}).get('channels')
    except (OSError,KeyError):pass
    return None


def open_capture(pid,requested,factory,cancel=lambda:None,hint_reader=process_hint):
    hint=hint_reader(pid) if requested==0 else None
    for channels in candidates(requested,hint):
        cancel()
        try:return factory(pid,channels),channels,hint
        except RuntimeError as exc:
            # Only explicit format rejection permits another process-only
            # format. Access denial, target exit, timeouts, etc. stay errors.
            message=str(exc).upper()
            unsupported='INITIALIZE' in message and any(code in message for code in ('0X88890008','0X80070057'))
            if requested or channels==2 or not unsupported:raise
    raise RuntimeError('No supported capture format')
