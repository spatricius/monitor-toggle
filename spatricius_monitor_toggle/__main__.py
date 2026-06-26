import signal

from gi.repository import GLib

from .lock import acquire_lock
from .app import MonitorIndicator
from .constants import LOCK_FILE


def main():
    lock_fd = acquire_lock(LOCK_FILE)
    loop = GLib.MainLoop()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, loop.quit)
    indicator = MonitorIndicator(loop)
    indicator.start()
    try:
        loop.run()
    except SystemExit:
        pass
    finally:
        import os
        os.close(lock_fd)
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
