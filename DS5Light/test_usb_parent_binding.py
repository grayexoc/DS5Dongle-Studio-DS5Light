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
        self.assertEqual(b.output([row]),row)

    def test_other_usb_device_rejected_even_when_unique(self):
        b=self.binding();row=self.row(usb_parent_id='usb-other')
        self.assertIsNone(b.output([row]))
        self.assertFalse(b.confirm_output(row,allow_container_mismatch=True))

    def test_reenumeration_and_manual_name_selection(self):
        b=self.binding();b.bind_output(self.row())
        new=self.row(endpoint_id='new-after-mode-switch',name='DualSense Edge')
        self.assertEqual(b.output([new]),new)
        self.assertIsNone(b.output([new],name='Other manual selection'))

    def test_two_matching_endpoints_require_manual_selection(self):
        b=self.binding();a=self.row();c=self.row(endpoint_id='second')
        self.assertIsNone(b.output([a,c]))

    def test_single_output_requires_identity_evidence(self):
        b=DeviceBinding();b._identity=DeviceIdentity(hid_path=b'hid',serial='pico',container_id='hid')
        row=self.row()
        self.assertIsNone(b.output([row]))
        self.assertEqual(b.output([dict(row,container_id='hid')])['endpoint_id'],'audio')

    def test_planned_usb_mode_switch_checks_cached_port_and_unique_hid(self):
        native=dict(path=b'vid_054c',vendor_id=0x054c,product_id=0x0df2,usb_parent_id='native')
        xbox=dict(path=b'vid_1209',vendor_id=0x1209,product_id=1,usb_parent_id='xbox',serial_number='pico')
        with patch('windows_device_identity.usb_port_paths',side_effect=lambda p:('port',) if p in ('native','xbox') else ()):
            b=DeviceBinding()
            b.bind_hid(native)
            b.bind_output(self.row())
            self.assertIsNone(b.resolve_hid([xbox]))
            b.expect_reconnect(usb_mode_change=True)
            self.assertIsNone(b.resolve_hid([dict(xbox,usb_parent_id='other')]))
            self.assertIsNone(b.resolve_hid([xbox,dict(xbox,path=b'duplicate')]))
            self.assertEqual(b.resolve_hid([xbox]),xbox)
            b.bind_hid(xbox)
            self.assertIsNone(b.snapshot().endpoint_id)
            self.assertIsNone(b.resolve_hid([native]))
            b.expect_reconnect(usb_mode_change=True)
            self.assertEqual(b.resolve_hid([native]),native)
            b.bind_hid(native)
            self.assertEqual(b.snapshot().serial,'pico')
            b.expect_reconnect(usb_mode_change=True)
            self.assertIsNone(b.resolve_hid([dict(xbox,serial_number='different')]))

    def test_stale_manual_confirmation_is_rejected(self):
        b=self.binding();before=b.snapshot()
        b._identity=DeviceIdentity(hid_path=b'other')
        self.assertFalse(b.confirm_output(self.row(),allow_container_mismatch=True,expected_identity=before))
        self.assertIsNone(b.snapshot().endpoint_id)

    def test_native_lookup_when_metadata_is_missing(self):
        b=self.binding();row=self.row();row.pop('usb_parent_id')
        with patch('windows_device_identity.usb_parent_id',return_value='usb-pico') as lookup:
            self.assertEqual(b.output([row])['endpoint_id'],'audio')
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
