"""Keep Tk finalizers out of Thread.start's startup handshake."""
import gc
import threading

_start_lock = threading.Lock()

def start_thread(thread):
    # Tk Variable.__del__ can wait for the UI while Thread.start waits for this thread.
    with _start_lock:
        enabled = gc.isenabled()
        gc.disable()
        try:
            thread.start()
        finally:
            if enabled:
                gc.enable()
