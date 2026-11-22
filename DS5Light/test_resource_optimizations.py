"""Keep the existing DSP output while using the cheaper single-section path."""
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch
import numpy as np
from scipy.signal import sosfilt, butter
from core import Controls, Processor, RATE
from audio import OutputProcessor


def legacy_section(b, a, x, axis=0, zi=None):
    y, state = sosfilt(np.concatenate((b, a))[None], x, axis=axis, zi=zi[None])
    return y, state[0]


class ResourceOptimizationTests(unittest.TestCase):
    def test_signal_filters_load_only_when_filtering_is_requested(self):
        script = textwrap.dedent("""
            import sys
            from types import SimpleNamespace
            from unittest.mock import patch

            import app
            from audio import Engine, OutputProcessor
            from core import Controls, StreamingResampler

            def start(engine, check):
                with patch('audio.bridge_conflict'), patch.object(engine, '_run', check):
                    engine.start()
                    engine.thread.join(10)
                assert not engine.thread.is_alive()
                assert engine.errors == 0, engine.status

            def cold():
                assert 'scipy.signal' not in sys.modules

            cold()
            StreamingResampler(48000)
            off = Controls(bypass=True)
            on = Controls()
            pcm = bytes((0, 32)) * (240 * 4)
            engine = Engine(controls=off)
            start(engine, cold)
            assert engine.output_processor.process(pcm, off) == pcm
            assert engine.output_processor.processor is None
            cold()

            ui = SimpleNamespace(engine=engine, controls=off, _stopping=False,
                                 studio=SimpleNamespace(rear_control_required=lambda: False),
                                 _read_controls=lambda: on, render=lambda: None)
            load = app.load_signal_filters

            def load_before_enabling():
                assert engine.controls == off
                return load()

            with patch.object(app, 'load_signal_filters', load_before_enabling):
                app.App.update_controls(ui)
            assert engine.controls == on
            assert 'scipy.signal' in sys.modules
            expected = OutputProcessor().process(pcm, on)
            assert engine.output_processor.process(pcm, on) == expected
            assert engine.output_processor.process(pcm, off) == pcm
            assert engine.output_processor.process(pcm, on) == expected

            startup = Engine(controls=on)
            def prepared():
                assert startup.output_processor.processor is not None
                assert startup.output_processor.process(pcm, on) == expected
            start(startup, prepared)
        """)
        result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pcm_matches_existing_path_across_signals_and_control_transitions(self):
        actual, reference = OutputProcessor(), OutputProcessor()
        rng = np.random.default_rng(81)
        position = 0
        for i in range(1200):
            n = (240, 480, 120, 960)[i % 4]
            t = (position + np.arange(n)) / RATE
            x = .22 * np.sin(2*np.pi*(55, 120, 600, 2500, 8000)[i % 5]*t)
            stereo = np.column_stack((x, -x if i % 3 else x))
            stereo += rng.normal(0, .005, stereo.shape)
            if i % 7 == 0:stereo[:] = 0
            if i % 11 == 0:stereo[0] = (.95, -.95)
            pcm = np.tile(np.rint(stereo*32767).astype('<i2'), (1, 2)).tobytes()
            c = Controls(bypass=i % 23 < 3, background=i % 19 != 0,
                         strength=(i % 10)/10, impact=(i % 8)/8,
                         gain=(0., .5, 1., 1.5)[(i//30) % 4])
            front = i % 13 < 3
            output = actual.process(pcm, c, front_only=front)
            with patch('scipy.signal.lfilter', legacy_section):
                expected = reference.process(pcm, c, front_only=front)
            self.assertEqual(output, expected, f'block {i}')
            position += n

    def test_multiple_sections_keep_sos_filter_and_state_shape(self):
        p = Processor()
        p.sos[0] = butter(4, 120, fs=RATE, output='sos')
        p.zi[0] = np.zeros((2, 2, 2))
        x = np.random.default_rng(2).normal(0, .1, (240, 2))
        with patch('scipy.signal.sosfilt', wraps=sosfilt) as fallback:
            for _ in range(3):self.assertTrue(np.isfinite(p.process(x)).all())
        self.assertEqual(fallback.call_count, 3)
        self.assertEqual(p.zi[0].shape, (2, 2, 2))


if __name__ == '__main__':unittest.main()
