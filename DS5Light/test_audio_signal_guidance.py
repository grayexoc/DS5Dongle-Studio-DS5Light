"""Existing interval counters distinguish no input from end-block silence."""
import struct,unittest
from unittest.mock import Mock,patch
from device_diagnostics import audio_signal_guidance,finish_speaker_measurement
from test_device_diagnostics import response


class GuidanceTests(unittest.TestCase):
    def report(self,**changes):
        observation=dict(blocks_delta=100,interval_ms=5000,channels=4,auto_haptics=0,
                         usb_mode='DualSense',front_peak=0,rear_left_peak=0,rear_right_peak=0)
        observation.update(changes)
        return dict(status=dict(ready=True,auto_haptics=0,usb_mode='DualSense',speaker_diagnostics=True),audio_observation=observation)

    def test_no_new_blocks_never_uses_old_nonzero_peaks_as_current_input(self):
        text=audio_signal_guidance(self.report(blocks_delta=0,front_peak=100,rear_left_peak=200))
        self.assertIn('새 USB 오디오 수신이 없습니다',text)

    def test_silent_four_channel_and_speaker_only_are_distinct(self):
        self.assertIn('4채널 신호는 거의 무음',audio_signal_guidance(self.report(front_peak=1)))
        self.assertIn('스피커 신호는 수신',audio_signal_guidance(self.report(front_peak=100)))

    def test_a_single_nonzero_haptic_channel_is_not_labelled_silent(self):
        text=audio_signal_guidance(self.report(rear_right_peak=2))
        self.assertIn('신호가 감지',text);self.assertIn('확인한 결과는 아닙니다',text)

    def test_two_channel_audio_is_not_declared_missing_haptics(self):
        self.assertIn('4채널이 아닙니다',audio_signal_guidance(self.report(channels=2)))

    def test_mix_xinput_unsupported_and_failed_checks_do_not_claim_silence(self):
        for key,value in (('auto_haptics',1),('auto_haptics',2),('usb_mode','XInput')):
            report=self.report();report['status'][key]=value
            self.assertIn('DualSense 모드',audio_signal_guidance(report))
        report=self.report();report.pop('audio_observation')
        self.assertIn('5초 검사',audio_signal_guidance(report))
        report['status'].pop('speaker_diagnostics');self.assertIn('구분할 수 없습니다',audio_signal_guidance(report))
        report=self.report();report['page_errors']={'speaker_delta':''}
        self.assertIn('확인하지 못했습니다',audio_signal_guidance(report))

    def test_real_measurement_uses_counter_delta_and_final_block_with_wrap(self):
        before=response();before[9]=3;before[10]=0;before[11]=0;before[12]=4;before[47]=1
        struct.pack_into('<I',before,43,1000);struct.pack_into('<HHI',before,48,50,50,0xffffffff)
        after=before[:];struct.pack_into('<I',after,43,6000);struct.pack_into('<H',after,13,0)
        struct.pack_into('<HHI',after,48,0,0,1)
        counters=response(2)
        from device_diagnostics import decode_status,SPEAKER_COUNTERS
        report=dict(status=decode_status(before),speaker_counters=dict.fromkeys(SPEAKER_COUNTERS,0))
        with patch('device_diagnostics.tagged_command',side_effect=[after,counters]):finish_speaker_measurement(Mock(),report,6000,lambda:False)
        self.assertEqual(report['audio_observation']['blocks_delta'],2)
        self.assertEqual(report['audio_observation']['rear_left_peak'],0)
        self.assertIn('마지막으로 읽은 4채널',audio_signal_guidance(report))


if __name__=='__main__':unittest.main()
