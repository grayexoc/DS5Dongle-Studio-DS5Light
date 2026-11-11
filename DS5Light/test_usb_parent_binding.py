import unittest
from unittest.mock import patch
from device_binding import DeviceBinding,DeviceIdentity
from windows_device_identity import _usb_ancestor


class ParentBindingTests(unittest.TestCase):
    def binding(self):
        b=DeviceBinding()
        b._identity=DeviceIdentity(hid_path=b'hid',serial='pico',container_id='hid',usb_parent_id='usb-pico')
        return b

    def row(self,**kw):
        return dict(dict(name='DualSense',maxOutputChannels=4,endpoint_id='audio',container_id='audio',usb_parent_id='usb-pico'),**kw)

    def test_ancestor_follows_function_to_physical_usb(self):
        names={0:r'HID\VID_054C&PID_0CE6&MI_03\child',1:r'USB\VID_054C&PID_0CE6&MI_03\function',2:r'USB\VID_054C&PID_0CE6\0123456789ABCDEF'}
        self.assertEqual(_usb_ancestor(0,lambda n:n+1,names.get),names[2].casefold())
        self.assertIsNone(_usb_ancestor(0,lambda n:0,lambda n:'virtual'))
        self.assertIsNone(_usb_ancestor(0,lambda n:None,lambda n:None))

    def test_same_physical_device_ignores_interface_container_difference(self):
        b=self.binding();row=self.row()
        self.assertEqual(b.match_output([row]),row)

    def test_other_usb_device_rejected_even_when_unique(self):
        b=self.binding();row=self.row(usb_parent_id='usb-other')
        hids=[dict(path=b'hid',serial_number='pico')]
        self.assertIsNone(b.match_output([row],hids))
        self.assertFalse(b.confirm_output(row,allow_container_mismatch=True))

    def test_reenumeration_and_manual_name_selection(self):
        b=self.binding();b.bind_output(self.row())
        new=self.row(endpoint_id='new-after-mode-switch',name='DualSense Edge')
        self.assertEqual(b.match_output([new]),new)
        self.assertIsNone(b.match_output([new],name='Other manual selection'))

    def test_two_matching_endpoints_require_manual_selection(self):
        b=self.binding();a=self.row();c=self.row(endpoint_id='second')
        self.assertIsNone(b.match_output([a,c]))

    def test_existing_single_pair_fallback_is_shared(self):
        b=DeviceBinding();b._identity=DeviceIdentity(hid_path=b'hid',serial='pico',container_id='hid')
        row=self.row();hids=[dict(path=b'hid',serial_number='pico')]
        self.assertEqual(b.match_output([row],hids),row)
        b=DeviceBinding();b._identity=DeviceIdentity(hid_path=b'hid',serial='pico',container_id='hid')
        self.assertIsNone(b.match_output([row],hids*2))

    def test_stale_manual_confirmation_is_rejected(self):
        b=self.binding();before=b.snapshot()
        b._identity=DeviceIdentity(hid_path=b'other')
        self.assertFalse(b.confirm_output(self.row(),allow_container_mismatch=True,expected_identity=before))
        self.assertIsNone(b.snapshot().endpoint_id)

    def test_native_lookup_when_metadata_is_missing(self):
        b=self.binding();row=self.row();row.pop('usb_parent_id')
        with patch('windows_device_identity.usb_parent_id',return_value='usb-pico') as lookup:
            self.assertEqual(b.match_output([row])['endpoint_id'],'audio')
            lookup.assert_called_with('audio',endpoint=True)

    def test_hid_mode_switch_without_serial_recovers_by_usb_parent(self):
        b=self.binding();b.bind_output(self.row())
        row=dict(path=b'new-mode-hid',container_id='new-interface',usb_parent_id='usb-pico')
        self.assertEqual(b.resolve_hid([row]),row)
        b.bind_hid(row)
        self.assertEqual(b.snapshot().endpoint_id,'audio')
        self.assertEqual(b.snapshot().serial,'pico')

    def test_parent_recovery_never_overrides_serial_conflict(self):
        b=self.binding()
        row=dict(path=b'other',serial_number='different',container_id='other',usb_parent_id='usb-pico')
        self.assertIsNone(b.resolve_hid([row]))
        b.bind_hid(row)
        self.assertIsNone(b.snapshot().endpoint_id)


if __name__=='__main__':unittest.main()
