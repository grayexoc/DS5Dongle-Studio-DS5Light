import unittest
import numpy as np
from core import Processor

class ImpactGapTests(unittest.TestCase):
    def test_gap_closes_faster_without_changing_attack(self):
        a,b=Processor(),Processor()
        a.gain[:]=b.gain[:]=1
        target=np.full(4,.2)
        slow=a._gain_ramp(target,240).copy()
        fast=b._gain_ramp(target,240,np.ones(4,dtype=bool)).copy()
        self.assertTrue(np.all(fast[:,-1]<slow[:,-1]))
        self.assertTrue(np.all(fast>=.2))
        a.gain[:]=b.gain[:]=.2
        target[:]=1
        np.testing.assert_array_equal(a._gain_ramp(target,240),b._gain_ramp(target,240,np.ones(4,dtype=bool)))

    def test_profile_default_is_not_changed(self):
        from studio_backup import _SLOT_DEFAULTS as DEFAULTS
        self.assertEqual(DEFAULTS['rumble_haptic_strength'],50)
