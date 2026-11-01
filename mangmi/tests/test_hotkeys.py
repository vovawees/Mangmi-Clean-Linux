# SPDX-License-Identifier: GPL-2.0-or-later
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mangmi.hotkeyd import HOLD_SECONDS, Combos  # noqa: E402


class CombosTest(unittest.TestCase):
    def test_tap_needs_guide(self):
        c = Combos()
        self.assertEqual(c.feed("up", True, 0), [])
        c.feed("up", False, 0.1)
        c.feed("guide", True, 1)
        self.assertEqual(c.feed("up", True, 1.1), ["brightness-up"])
        self.assertEqual(c.feed("up", True, 1.2), [])          # no repeat while held
        c.feed("up", False, 1.3)
        self.assertEqual(c.feed("r3", True, 1.4), ["led-next"])

    def test_hold(self):
        c = Combos()
        c.feed("guide", True, 0)
        c.feed("select", True, 0.1)
        self.assertEqual(c.due(0.1 + HOLD_SECONDS - 0.01), [])
        self.assertEqual(c.due(0.1 + HOLD_SECONDS), ["mode-toggle"])
        self.assertEqual(c.due(10), [])                          # fires once

    def test_hold_cancelled_by_release(self):
        c = Combos()
        c.feed("guide", True, 0)
        c.feed("start", True, 0)
        c.feed("guide", False, 0.5)
        self.assertEqual(c.due(5), [])
        c.feed("guide", True, 6)
        c.feed("start", False, 6)   # start released first
        self.assertIsNone(c.next_deadline())

    def test_guide_alone_does_nothing(self):
        c = Combos()
        self.assertEqual(c.feed("guide", True, 0), [])
        self.assertEqual(c.feed("guide", False, 0.2), [])
        self.assertEqual(c.due(9), [])


if __name__ == "__main__":
    unittest.main()
