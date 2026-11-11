"""Pending Studio completion must not override a later stop or route change."""
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from run_intent import RunIntent
from studio_settings_ui import StudioSettings


class ResumeTests(unittest.TestCase):
    def test_capture_token_after_internal_stop(self):
        intent=RunIntent();intent.request('route')
        app=SimpleNamespace(engine=object(),studio=SimpleNamespace(busy=False),
                            run_intent=intent,_run_route=lambda:'route',_close_requested=False)
        app.stop=lambda on_complete:(intent.stop(),on_complete())
        ui=SimpleNamespace(app=app,busy=False,cancel=threading.Event(),
                           progress=Mock(),render_fields=Mock(),task=Mock())
        StudioSettings.stopped_task(ui,'apply',lambda:None)
        self.assertTrue(ui.resume)
        self.assertEqual(ui._resume_token,(intent.generation,'route'))
        ui.task.assert_called_once()

    def pending_resume(self):
        intent=RunIntent();intent.request('route');intent.stop()
        app=SimpleNamespace(run_intent=intent,_run_route=Mock(return_value='route'),
                            _close_requested=False,start=Mock(),render=Mock(),last_render=None)
        results=queue.SimpleQueue();results.put(('probe',{'reconnect':True},None))
        ui=SimpleNamespace(closed=False,busy=False,resume=True,results=results,
                           cancel=threading.Event(),app=app,parent=Mock(),
                           render_fields=Mock(),update_state=Mock(),
                           _resume_token=(intent.generation,'route'))
        StudioSettings.poll(ui)
        delay,callback=ui.parent.after.call_args.args
        self.assertEqual(delay,700)
        return ui,callback

    def test_unchanged_intent_resumes(self):
        ui,callback=self.pending_resume();callback();ui.app.start.assert_called_once()

    def test_later_stop_or_route_change_cancels_resume(self):
        for change in ('stop','route','close','cancel','busy','start'):
            with self.subTest(change=change):
                ui,callback=self.pending_resume()
                if change=='stop':ui.app.run_intent.stop()
                elif change=='route':ui.app._run_route.return_value='other'
                elif change=='close':ui.closed=True
                elif change=='cancel':ui.cancel.set()
                elif change=='busy':ui.busy=True
                else:ui.app.run_intent.request('route')
                callback();ui.app.start.assert_not_called()


if __name__=='__main__':unittest.main()
