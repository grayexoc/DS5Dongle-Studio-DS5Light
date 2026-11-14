"""One selected physical device: immutable snapshots shared across workers."""
from dataclasses import dataclass,replace
from threading import RLock

@dataclass(frozen=True)
class DeviceIdentity:
    hid_path:object=None
    serial:str|None=None
    container_id:str|None=None
    endpoint_id:str|None=None
    endpoint_name:str|None=None
    confirmed_container_id:str|None=None
    usb_parent_id:str|None=None
    edge_serial_present:bool|None=None
    require_output_identity:bool=False
    expected_edge_serial:bool|None=None
    edge_port_paths:tuple[str,...]=()


def resolve_hid(rows,path=None,serial=None,container_id=None,allow_unique=False):
    rows=list(rows)
    if serial:
        matches=[r for r in rows if r.get('serial_number')==serial]
        if len(matches)==1:return matches[0]
        if len(matches)>1:
            exact=[r for r in matches if r['path']==path and (not container_id or not r.get('container_id') or r['container_id']==container_id)]
            return exact[0] if len(exact)==1 else None
        if container_id:
            matches=[r for r in rows if r.get('container_id')==container_id and not r.get('serial_number')]
            if len(matches)==1:return matches[0]
        return None
    if container_id:
        matches=[r for r in rows if r.get('container_id')==container_id]
        return matches[0] if len(matches)==1 else None
    if path is not None:
        matches=[r for r in rows if r['path']==path]
        return matches[0] if len(matches)==1 else None
    return rows[0] if allow_unique and len(rows)==1 else None

class DeviceBinding:
    def __init__(self):self._identity=DeviceIdentity();self._lock=RLock();self.fast_until=0.
    def snapshot(self):
        with self._lock:return self._identity
    def bind_hid(self,row):
        from windows_device_identity import hid_container,usb_parent_id,usb_port_paths
        parent=row.get('usb_parent_id') or usb_parent_id(row['path'])
        container=row.get('container_id') or hid_container(row['path'])
        with self._lock:
            old=self._identity
            conflict=bool(old.serial and row.get('serial_number') and row['serial_number']!=old.serial)
            same_port=(old.edge_port_paths and old.expected_edge_serial is not None and row.get('product_id') in (0x0ce6,0x0df2) and
                       bool(row.get('serial_number'))==old.expected_edge_serial and
                       bool(set(old.edge_port_paths).intersection(usb_port_paths(parent))))
            same=not conflict and ((old.serial and row.get('serial_number')==old.serial) or old.hid_path==row['path'] or
                                   (parent and parent==old.usb_parent_id) or same_port)
            edge_serial=(bool(row.get('serial_number')) if row.get('product_id') in (0x0ce6,0x0df2) else
                         old.edge_serial_present if same and 'product_id' not in row else None)
            changed=(edge_serial is not None and old.edge_serial_present is not None and
                     edge_serial!=old.edge_serial_present)
            expected=old.expected_edge_serial
            if (edge_serial is not None and edge_serial==expected) or ('product_id' in row and edge_serial is None):
                expected=None
            strict=changed or (old.require_output_identity and
                               (edge_serial is not None or ('product_id' not in row and same)))
            keep_endpoint=same and not strict
            self._identity=DeviceIdentity(row['path'],row.get('serial_number') or (old.serial if same else None),
                container or (old.container_id if same and not strict else None),old.endpoint_id if keep_endpoint else None,
                old.endpoint_name if keep_endpoint else None,old.confirmed_container_id if keep_endpoint else None,
                parent or (old.usb_parent_id if same else None),edge_serial,strict,expected,
                old.edge_port_paths if expected is not None else ())
        return self.snapshot()
    def resolve_hid(self,rows,allow_unique=False):
        value=self.snapshot();rows=list(rows)
        if value.container_id and (not value.serial or not any(r.get('serial_number')==value.serial for r in rows)):
            from windows_device_identity import hid_container
            rows=[dict(row,container_id=row.get('container_id') or hid_container(row['path'])) for row in rows]
        match=resolve_hid(rows,value.hid_path,value.serial,value.container_id,allow_unique)
        if match is not None or not value.usb_parent_id:return match
        from windows_device_identity import usb_parent_id
        same=[row for row in rows if not (value.serial and row.get('serial_number') and row['serial_number']!=value.serial)
              and (row.get('usb_parent_id') or usb_parent_id(row['path']))==value.usb_parent_id]
        return same[0] if len(same)==1 else None

    def resolve_edge_reconnect(self,rows,serial_present):
        from windows_device_identity import usb_parent_id,usb_port_paths
        value=self.snapshot()
        rows=[row for row in rows if row.get('product_id') in (0x0ce6,0x0df2) and
              bool(row.get('serial_number'))==serial_present]
        match=self.resolve_hid(rows)
        if match is not None or value.expected_edge_serial!=serial_present or not value.edge_port_paths:return match
        ports=set(value.edge_port_paths)
        matches=[row for row in rows if not (value.serial and row.get('serial_number') and row['serial_number']!=value.serial)
                 and ports.intersection(usb_port_paths(row.get('usb_parent_id') or usb_parent_id(row['path'])))]
        return matches[0] if len(matches)==1 else None

    def expect_edge_serial_reconnect(self,*,hidden):
        from windows_device_identity import usb_port_paths
        # Windows can assign a new container and endpoint to the same Pico.
        with self._lock:
            self._identity=replace(self._identity,endpoint_id=None,endpoint_name=None,
                                   confirmed_container_id=None,require_output_identity=True,expected_edge_serial=not hidden,
                                   edge_port_paths=usb_port_paths(self._identity.usb_parent_id))

    def output(self,rows,name=None):
        value=self.snapshot();rows=list(rows)
        if value.expected_edge_serial is not None:return None
        candidates=[r for r in rows if r.get('maxOutputChannels',0)>=4 and not r.get('isLoopbackDevice')]
        if value.usb_parent_id:
            from windows_device_identity import usb_parent_id
            candidates=[dict(r,usb_parent_id=r.get('usb_parent_id') or usb_parent_id(r.get('endpoint_id'),endpoint=True)) for r in candidates]
            candidates=[r for r in candidates if not r.get('usb_parent_id') or r['usb_parent_id']==value.usb_parent_id]
            same=[r for r in candidates if r.get('usb_parent_id')==value.usb_parent_id]
            if len(same)==1 and (name is None or same[0].get('name')==name or value.endpoint_name==name):return same[0]
        if value.require_output_identity:
            matches=[r for r in candidates if value.container_id and r.get('container_id')==value.container_id
                     and (name is None or r.get('name')==name)]
            return matches[0] if len(matches)==1 else None
        # Exact endpoint identity survives a missing container property, but
        # never overrides positive evidence that this is another device.
        exact=[r for r in candidates if value.endpoint_id and r.get('endpoint_id')==value.endpoint_id
               and not (value.container_id and r.get('container_id') and r['container_id']!=value.container_id
                        and r.get('container_id')!=value.confirmed_container_id)]
        if len(exact)==1 and (name is None or value.endpoint_name is None or name==value.endpoint_name or exact[0]['name']==name):return exact[0]
        if name is not None and value.endpoint_name is not None and name!=value.endpoint_name:
            requested=[r for r in candidates if r['name']==name]
            same=[r for r in requested if (value.container_id and r.get('container_id')==value.container_id)
                  or (value.endpoint_id and r.get('endpoint_id')==value.endpoint_id and not (value.container_id and r.get('container_id') and r['container_id']!=value.container_id))]
            if len(same)==1:return same[0]
            if requested:return None

        if value.confirmed_container_id:
            confirmed=[r for r in candidates if r.get('container_id')==value.confirmed_container_id]
            if len(confirmed)==1:return confirmed[0]
        if value.container_id:
            candidates=[r for r in candidates if r.get('container_id')==value.container_id]
        elif value.endpoint_id:
            candidates=[r for r in candidates if r.get('endpoint_id')==value.endpoint_id]
        else:
            candidates=[r for r in candidates if any(name in r.get('name','').lower() for name in ('dualsense','studio xinput experiment'))]
        exact=[r for r in candidates if value.endpoint_id and r.get('endpoint_id')==value.endpoint_id]
        if len(exact)==1:return exact[0]
        if name is not None and not value.endpoint_id:
            named=[r for r in candidates if r.get('name')==name]
            if named or not value.container_id:
                candidates=named
        return candidates[0] if len(candidates)==1 else None
    def match_output(self, rows, hid_rows=(), name=None):
        """Shared by audio startup and diagnostics; ambiguous devices need confirmation."""
        rows=list(rows)
        with self._lock:
            row=self.output(rows,name)
            if row is not None:return row
            if self.auto_pair_output(rows,hid_rows,name):return self.output(rows,name)
            return None

    def auto_pair_output(self, rows, hid_rows, name=None):
        """Compatibility pairing for one Studio device and one DualSense output."""
        hid_rows = list(hid_rows)
        identity = self.snapshot()
        if identity.require_output_identity or len(hid_rows) != 1 or self.resolve_hid(hid_rows) is None:
            return False
        candidates = [row for row in rows
                      if row.get('maxOutputChannels', 0) >= 4
                      and not row.get('isLoopbackDevice')
                      and 'dualsense' in row.get('name', '').lower()]
        if len(candidates) != 1:
            return False
        row = candidates[0]
        if name is not None and name != row.get('name'):
            return False
        if self.snapshot() != identity:
            return False
        return self.confirm_output(row, allow_container_mismatch=True, expected_identity=identity)

    def confirm_output(self,row,*,allow_container_mismatch=False,expected_identity=None):
        with self._lock:
            if expected_identity is not None and self._identity!=expected_identity:return False
            value=self.snapshot()
            if value.expected_edge_serial is not None or not value.hid_path or not row.get('endpoint_id') or row.get('maxOutputChannels',0)<4 or row.get('isLoopbackDevice'):
                return False
            if value.usb_parent_id:
                from windows_device_identity import usb_parent_id
                parent=row.get('usb_parent_id') or usb_parent_id(row.get('endpoint_id'),endpoint=True)
                if parent and parent!=value.usb_parent_id:return False
            if value.container_id and row.get('container_id') and value.container_id!=row['container_id'] and not allow_container_mismatch:
                return False
            self._identity=replace(self._identity,confirmed_container_id=row.get('container_id') if allow_container_mismatch else None,require_output_identity=False)
            self.bind_output(row)
            return True
    def output_issue(self,rows):
        candidates=[r for r in rows if r.get('maxOutputChannels',0)>=4 and not r.get('isLoopbackDevice')]
        if not candidates:return 'missing'
        if len(candidates)>1 and len({r.get('name') for r in candidates})<len(candidates):return 'ambiguous'
        return 'identity'
    def bind_output(self,row):
        with self._lock:self._identity=replace(self._identity,endpoint_id=row.get('endpoint_id') or self._identity.endpoint_id,endpoint_name=row.get('name'))
    def expect_reconnect(self,seconds=8):
        import time
        with self._lock:self.fast_until=max(self.fast_until,time.monotonic()+seconds)
