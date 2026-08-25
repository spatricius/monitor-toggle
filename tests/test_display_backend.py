import unittest
from types import SimpleNamespace
from unittest.mock import patch

from spatricius_monitor_toggle import display_backend as db


def fake_backend(**funcs):
    return SimpleNamespace(**funcs)


class CallFallbackTests(unittest.TestCase):
    """_call() caches one backend module (kscreen/mutter/xrandr) and only
    re-detects on failure, so a working session doesn't pay a detection cost
    on every call - but a backend that starts failing must not get stuck."""

    def test_calls_the_cached_backend_directly_on_success(self):
        backend = fake_backend(get_outputs=lambda: ["ok"])
        with patch.object(db, "_backend", backend), \
             patch.object(db, "_detect_backend") as detect:
            result = db._call("get_outputs")

        self.assertEqual(result, ["ok"])
        detect.assert_not_called()

    def test_retries_with_a_newly_detected_backend_after_failure(self):
        def boom():
            raise RuntimeError("service gone")

        failing = fake_backend(get_outputs=boom)
        working = fake_backend(get_outputs=lambda: ["fresh"])

        with patch.object(db, "_backend", failing), \
             patch.object(db, "_detect_backend", return_value=working):
            result = db._call("get_outputs")
            self.assertIs(db._backend, working)

        self.assertEqual(result, ["fresh"])

    def test_reraises_when_redetection_yields_the_same_backend(self):
        def boom():
            raise RuntimeError("still gone")

        failing = fake_backend(get_outputs=boom)

        with patch.object(db, "_backend", failing), \
             patch.object(db, "_detect_backend", return_value=failing):
            with self.assertRaises(RuntimeError):
                db._call("get_outputs")


if __name__ == "__main__":
    unittest.main()
