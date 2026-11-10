"""Recent transport health; sampling happens only when diagnostics are visible."""
from studio_i18n import text as _ui_tr
import time


class StreamHealth:
    def __init__(self): self.previous=None; self.unstable_until=0.
    def sample(self,phase,last_block,blocks,errors,drops,stale,now=None):
        now=time.monotonic() if now is None else now
        current=(now,errors,drops,stale)
        elapsed=0.; delta_errors=delta_drops=delta_stale=0
        if self.previous and 0<now-self.previous[0]<=5:
            elapsed=now-self.previous[0]
            delta_errors=max(0,errors-self.previous[1]); delta_drops=max(0,drops-self.previous[2]); delta_stale=max(0,stale-self.previous[3])
            if delta_errors or delta_drops or delta_stale: self.unstable_until=now+5
        self.previous=current
        if phase=='waiting': label=_ui_tr('장치 연결 대기')
        elif phase=='starting': label=_ui_tr('연결 중')
        elif phase in ('error','stopped'): label=_ui_tr('캡처 중단')
        elif not blocks or last_block is None or now-last_block>2: label=_ui_tr('전송 대기')
        elif now<self.unstable_until: label=_ui_tr('전송 불안정')
        else: label=_ui_tr('정상')
        return dict(label=label,seconds=elapsed,drops=delta_drops,stale=delta_stale,errors=delta_errors)
