import ctypes as C
import unittest
from unittest.mock import patch,Mock
from device_binding import DeviceIdentity
import studio_volume as volume

class VolumeTests(unittest.TestCase):
    def test_estimate_matches_observed_points_and_is_monotonic(self):
        for value,percent in ((0,0),(40,1),(80,9),(100,25),(110,41),(127,100)):
            self.assertEqual(volume.estimated_windows_percent(value),percent)
        values=[volume.estimated_windows_percent(v) for v in range(128)]
        self.assertEqual(values,sorted(values))
        self.assertEqual(volume.estimated_windows_percent(90),17)
        for value in (-1,128,True):
            with self.assertRaises(ValueError):volume.estimated_windows_percent(value)
    def test_firmware_mapping_roundtrip_all_values(self):
        for value in range(128):
            db=volume.volume_db(value)
            self.assertEqual((round((db+100)*256)*127+12800)//25600,value)
        self.assertEqual(volume.volume_db(0),-100)
        self.assertEqual(volume.volume_db(127),0)
        for value in (-1,128,True,1.5):
            with self.assertRaises(ValueError):volume.volume_db(value)

    def test_requires_same_physical_device_not_name(self):
        identity=DeviceIdentity(hid_path=b'ours',container_id='ours')
        rows=[dict(id='a',container_id='other'),dict(id='b',container_id='ours')]
        self.assertEqual(volume.select_endpoint(identity,rows),'b')
        with self.assertRaises(OSError):volume.select_endpoint(identity,rows[:1])
        with self.assertRaises(OSError):volume.select_endpoint(identity,rows+[dict(id='c',container_id='ours')])
        with self.assertRaises(OSError):volume.select_endpoint(identity,[dict(id='b',container_id='ours',state=2)])
        strict=DeviceIdentity(hid_path=b'ours',endpoint_id='a',usb_parent_id='ours')
        with self.assertRaises(OSError):volume.select_endpoint(strict,[dict(id='a',usb_parent_id='other')])

    def test_sync_sets_only_selected_endpoint_once(self):
        binding=Mock();binding.snapshot.return_value=DeviceIdentity(hid_path=b'ours',container_id='ours')
        with patch.object(volume.audio,'snapshot',return_value=dict(endpoints=[dict(id='ours',container_id='ours')])) as snapshot,patch.object(volume,'set_endpoint_volume') as setter:
            volume.sync_speaker_volume(b'ours',binding,[],100)
            snapshot.assert_called_once_with(include_sessions=False)
            setter.assert_called_once_with('ours',100)

    def test_com_uses_db_and_releases_without_unmuting(self):
        ole=Mock();ole.CoInitializeEx.return_value=0;ole.CoCreateInstance.return_value=0
        calls=[]
        def invoke(pointer,index,types,*args):
            calls.append(index)
            if index==20:
                for target,value in zip(args,(-100,0,.5)):C.cast(target,C.POINTER(C.c_float))[0]=value
            if index==6:self.assertEqual(args,(volume.volume_db(100),None))
        with patch.object(C,'WinDLL',return_value=ole),patch.object(volume.audio,'_call',side_effect=invoke),patch.object(volume.audio,'_release') as release:
            volume.set_endpoint_volume('ours',100)
            self.assertEqual(calls,[5,3,20,6])
            self.assertEqual(release.call_count,3)
            ole.CoUninitialize.assert_called_once()

if __name__=='__main__':unittest.main()
