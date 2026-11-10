import ast
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from studio_backup import validate_backup
from studio_settings_protocol import SettingsClient


def app_function(name):
    tree = ast.parse(Path('app.py').read_text(encoding='utf-8'))
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


class AuditRegressionTests(unittest.TestCase):
    def test_old_backup_does_not_enable_excluded_custom_effects(self):
        rows, _ = validate_backup({'slots': [dict(index=0, valid=True, name='A',
            fields={'auto_haptics_gain': 100, 'ce_r2_enable': 1})]})
        self.assertEqual(rows[0]['fields']['auto_haptics_gain'], 100)
        self.assertNotIn('ce_r2_enable', rows[0]['fields'])

    def test_output_worker_always_reports_backend_failure(self):
        results = queue.SimpleQueue()
        scope = dict(results=results, devices=Mock(side_effect=ValueError('backend')),
                     time=SimpleNamespace(sleep=lambda _: None))
        node = app_function('collect_pair')
        with patch('studio_slots.devices', return_value=[]):
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                         'app.py', 'exec'), scope)
            scope['collect_pair']()
        rows, refreshed, error = results.get_nowait()
        self.assertEqual((rows, refreshed, error), ([], None, 'backend'))

    def test_start_callback_cannot_overlap_settings_transaction(self):
        app = SimpleNamespace(engine=None, _closing=False, _close_requested=False,
                              studio_settings=SimpleNamespace(busy=True))
        scope = dict(power_blocked=lambda _: False)
        node = app_function('_start_after_profile_check')
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                     'app.py', 'exec'), scope)
        scope['_start_after_profile_check'](app)

    def test_output_lookup_timeout_clears_pending_state(self):
        intent = SimpleNamespace(generation=1, stop=Mock())
        app = SimpleNamespace(_closing=False, _close_requested=False,
            _pair_lookup_pending=True, run_intent=intent,
            status=SimpleNamespace(set=Mock()), render=Mock())
        scope = dict(self=app, results=queue.SimpleQueue(), queue=queue,
            time=SimpleNamespace(monotonic=lambda: 11), lookup_deadline=10,
            generation=1, _ui_tr=lambda text: text, tr=lambda text: text)
        node = app_function('finish_pair')
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                     'app.py', 'exec'), scope)
        scope['finish_pair']()
        self.assertFalse(app._pair_lookup_pending)
        intent.stop.assert_called_once_with('output_lookup_error')

    def test_expired_snapshot_does_not_open_device(self):
        from studio_snapshot import snapshot
        with patch('studio_snapshot.devices', return_value=[]), patch('hid.device') as device:
            with self.assertRaises(TimeoutError):
                snapshot(None, deadline=0)
            device.assert_not_called()

    def test_dock_save_error_names_dock_policy(self):
        from studio_settings_protocol import PolicySaveError
        client = SettingsClient(None)
        with patch.object(client, 'command', return_value=bytes([102, 29, 2, 1, 0])):
            with self.assertRaisesRegex(PolicySaveError, '충전독') as caught:
                client.dock_disconnect(1)
        self.assertEqual(caught.exception.current, 0)
        self.assertIn('오디오', str(caught.exception))

    def test_brightness_off_is_hidden_but_legacy_value_is_valid(self):
        from studio_fields import FIELDS
        from studio_help import options
        from studio_settings_protocol import encode
        self.assertNotIn(3, dict(options(FIELDS['player_led_bright'])))
        self.assertEqual(encode(FIELDS['player_led_bright'], 3), b'\x03')
        self.assertIn(0, dict(options(FIELDS['player_led_mode'])))

    def test_transfer_lock_blocks_tab_and_field_changes(self):
        from studio_settings_ui import StudioSettings
        from app import App
        editor = SimpleNamespace(_transfer_job='backup')
        editor.transfer_locked = StudioSettings.transfer_locked.fget(editor)
        StudioSettings.select_category(editor, 1)
        StudioSettings.changed(editor, 'auto_haptics_gain', 120)
        App.select_tab(SimpleNamespace(studio_settings=editor), 0)
        editor._transfer_job = None
        self.assertFalse(StudioSettings.transfer_locked.fget(editor))

    def test_unchanged_slider_state_does_not_redraw(self):
        from app import HapticSlider
        slider = SimpleNamespace(enabled=True, configure=Mock(), draw=Mock())
        HapticSlider.set_enabled(slider, True)
        slider.draw.assert_not_called()
        HapticSlider.set_enabled(slider, False)
        slider.draw.assert_called_once()

    def test_dynamic_translation_cache_matches_and_is_bounded(self):
        import localization as language
        language._dynamic_english.cache_clear()
        text = '게임 전용 PID 9876'
        with patch.object(language, 'LANGUAGE', 'en'):
            expected = text
            for key in language.ORDERED:
                if key in expected:
                    expected = expected.replace(key, language.EN[key])
            self.assertEqual(language.tr(text), expected)
            self.assertEqual(language.tr(text), expected)
        self.assertEqual(language._dynamic_english.cache_info().hits, 1)
        self.assertEqual(language._dynamic_english.cache_info().maxsize, 512)

    def test_macro_view_signature_detects_in_place_edits(self):
        from studio_read_view import StableReadView
        editor = SimpleNamespace(category=4, loaded=True, write_ready=True,
            pico_recognized=True, path=b'pico',
            doc=SimpleNamespace(macros={'0': [0] * 35}, values={'macro_disable': 0}))
        before = StableReadView.extras_signature(editor)
        editor.doc.macros['0'][7] = 4
        self.assertNotEqual(before, StableReadView.extras_signature(editor))


if __name__ == '__main__':
    unittest.main()
