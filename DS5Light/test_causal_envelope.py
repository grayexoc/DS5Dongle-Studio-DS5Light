"""Existing detector retained; sample-accurate causal gain smoothing only."""
import importlib.util
import sys
from pathlib import Path
import unittest
import numpy as np
from core import Processor, Controls, RATE


def old_module():
    path=Path(__file__).parent/'tests/fixtures/causal-envelope/core.py'
    spec=importlib.util.spec_from_file_location('_envelope_baseline',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module


class CausalEnvelopeTests(unittest.TestCase):
    def test_exact_time_constants_and_endpoints(self):
        for n in (1,120,240,480,960):
            p=Processor();p._ensure_capacity(n)
            start=np.array([.25,.9,.45,.7]);target=np.array([.9,.3,.45,.2])
            p.gain=start.copy();ramp=p._gain_ramp(target,n).copy()
            tau=np.where(target>start,.003,.055)
            wanted=start[:,None]+(target-start)[:,None]*(-np.expm1(-np.arange(1,n+1)[None,:]/(RATE*tau[:,None])))
            np.testing.assert_allclose(ramp,wanted,atol=2e-15)
            np.testing.assert_allclose(p.gain,start+(target-start)*(1-np.exp(-n/RATE/tau)),atol=2e-15)

    def test_same_envelope_regardless_of_block_partition(self):
        for target in (np.full(4,.9),np.full(4,.2)):
            a=Processor();b=Processor();a.gain[:]=.5;b.gain[:]=.5
            a._ensure_capacity(480)
            whole=a._gain_ramp(target,480).copy()
            parts=np.concatenate([b._gain_ramp(target,240).copy() for _ in range(2)],axis=1)
            np.testing.assert_allclose(whole,parts,atol=2e-15)

    def test_first_attack_is_not_slower_than_old_chord(self):
        p=Processor();p.gain[:]=.3;target=np.ones(4)
        ramp=p._gain_ramp(target,240)[0].copy()
        end=.3+.7*(1-np.exp(-.005/.003))
        old=.3+(end-.3)*np.arange(1,241)/240
        self.assertTrue(np.all(ramp>=old-1e-15))
        self.assertAlmostEqual(ramp[-1],old[-1])

    def test_monotonic_bounded_no_overshoot(self):
        for target in (0.,.3,.8,1.):
            for start in (0.,.5,1.):
                p=Processor();p.gain[:]=start
                ramp=p._gain_ramp(np.full(4,target),240)
                self.assertGreaterEqual(float(ramp.min()),min(start,target)-1e-15)
                self.assertLessEqual(float(ramp.max()),max(start,target)+1e-15)
                self.assertTrue(np.all(np.diff(ramp,axis=1)*(target-start)>=-1e-15))

    def test_steady_gain_exact(self):
        p=Processor();p.gain[:]=.42
        np.testing.assert_array_equal(p._gain_ramp(np.full(4,.42),240),np.full((4,240),.42))

    def test_energy_envelopes_unchanged(self):
        old=old_module();a=Processor();b=old.Processor()
        rng=np.random.default_rng(991)
        for i in range(300):
            n=(120,240,480)[i%3]
            x=rng.normal(0,.08 if i%20<3 else .01,(n,2)).astype(np.float32)
            values=dict(strength=(.3,.55,.8)[i//100],transient=i%70<50,impact=.85,background=i%90<80,bypass=i%110>100)
            a.process(x,Controls(**values));b.process(x,old.Controls(**values))
            for field in ('fast_energy','slow_energy'):
                np.testing.assert_array_equal(getattr(a,field),getattr(b,field),err_msg=field)
            self.assertTrue(np.isfinite(a.gain).all())
            self.assertTrue(np.all((a.gain >= 0) & (a.gain <= 1)))

    def test_output_shape_finite_and_no_extra_tail(self):
        p=Processor()
        for n in (0,1,120,240,480):
            y=p.process(np.zeros((n,2),np.float32),Controls())
            self.assertEqual(y.shape,(n,2));self.assertTrue(np.isfinite(y).all())
            np.testing.assert_array_equal(y,np.zeros_like(y))

    def test_cached_settings_refresh_immediately(self):
        p=Processor();x=np.zeros((240,2),np.float32)
        a=Controls(strength=.3,impact=.2)
        p.process(x,a);self.assertIs(p._coefficient_controls,a)
        p.process(x,a);self.assertEqual(p._strength,.3);self.assertEqual(p._impact,.2)
        b=Controls(strength=.8,impact=.9,transient=False)
        p.process(x,b);self.assertIs(p._coefficient_controls,b)
        self.assertEqual(p._strength,.8);self.assertEqual(p._impact,0.)
        p.process(x,a);self.assertEqual(p._strength,.3);self.assertEqual(p._impact,.2)


if __name__=='__main__':unittest.main()
