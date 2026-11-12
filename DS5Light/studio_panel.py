"""One-row Studio profiles. Lazy reads, explicit activation, no idle polling."""

from thread_start import start_thread
from studio_i18n import text as _ui_tr

import queue

import threading

import time

import tkinter as tk

from tkinter import ttk,TclError

from localization import tr

from studio_slots import devices,run_device

from device_binding import DeviceBinding,resolve_hid

from studio_power import blocked as power_blocked



AUTOHAPTICS_OFF_MESSAGE=_ui_tr('현재 Studio 프로필의 오디오햅틱이 꺼져 있어 전송을 정지했습니다.')





class StudioPanel:

    def __init__(self,app,parent):

        self.app=app;self.parent=parent;self.busy=False;self.closed=False

        self.paths=[];self.slots=[];self.slot_paths=[];self.results=queue.SimpleQueue()

        self.poll_id=None;self.startup_id=None;self.last_read=-1e9;self.selected=None

        self.operation=None

        self._cancel=threading.Event();self._last_status=None

        self.auto_haptics_mode=None;self.profile_path=None;self.device_serials={}

        self._start_callback=None

        self.binding=DeviceBinding();self.observed_profile=None;self.last_profile_check=-1e9;self.catalog_invalid=False

        self.current_profile=None;self.current_profile_name=None;self.slot_labels=[]

        self._battery_ready_key=None;self._battery_recovery_pending=None

        self.controller_connected=None  # Unknown until a verified observation.

        row=ttk.Frame(parent);row.pack(fill='x');row.columnconfigure(2,weight=1)

        ttk.Label(row,text=tr(_ui_tr('Studio 프로필')),font=(_ui_tr('맑은 고딕'),11,'bold')).grid(row=0,column=0,sticky='w',padx=(0,12))

        self.profile_caption=ttk.Label(row,text=tr(_ui_tr('슬롯 목록')),style='Muted.TLabel')

        self.profile_caption.grid(row=0,column=1,sticky='w',padx=(0,8))

        self.choice=ttk.Combobox(row,state='readonly',width=14,postcommand=self.on_open)

        self.choice.grid(row=0,column=2,sticky='ew');self.choice.set(tr(_ui_tr('프로필 선택')))

        self.profile_text=tk.Canvas(self.choice,highlightthickness=0,bd=0,takefocus=0,cursor='hand2')

        self._profile_display=None

        self.profile_text.bind('<Button-1>',self._open_profile_popup)

        self.profile_text.bind('<MouseWheel>',lambda event:self.choice.event_generate('<MouseWheel>',delta=event.delta) if 'disabled' not in self.choice.state() else None)

        self.choice.bind('<Configure>',lambda event:self._draw_profile_text(),add='+')

        self.apply=ttk.Button(row,text=tr(_ui_tr('불러오기')),command=self.activate,width=9,state='disabled')

        self.apply.grid(row=0,column=3,sticky='ew',padx=(8,0))

        self.choice.bind('<<ComboboxSelected>>',lambda _e:self.render())



    def schedule_initial_read(self):

        if not self.closed and self.startup_id is None:self.startup_id=self.app.root.after(350,self.initial_read)



    def initial_read(self):

        self.startup_id=None

        self.discover(allow_running=True)



    def on_open(self):

        # Do not replace a populated popup while the user scrolls/selects it.

        # Startup, Start and post-activation reads keep the current slot fresh.

        if not self.busy and not self.slots:self.discover()

        self.parent.after_idle(self._color_profile_popup)



    def _open_profile_popup(self,event=None):

        if 'disabled' in self.choice.state():return

        self.choice.focus_set()

        self.choice.event_generate('<Button-1>',x=max(1,self.choice.winfo_width()-8),y=self.choice.winfo_height()//2)



    def _draw_profile_text(self):

        if not self._profile_display:return

        prefix,name=self._profile_display

        style=ttk.Style(self.parent)

        background=style.lookup('TCombobox','fieldbackground',self.choice.state()) or '#111110'

        font=style.lookup('TCombobox','font') or 'TkTextFont'

        self.profile_text.configure(bg=background,height=max(1,self.choice.winfo_height()-8))

        self.profile_text.place(x=9,y=4,relwidth=1,width=-33,height=max(1,self.choice.winfo_height()-8))

        self.profile_text.delete('all')

        y=max(1,self.choice.winfo_height()-8)/2

        text=self.profile_text.create_text(0,y,text=prefix,anchor='w',fill='#eee9df',font=font)

        bounds=self.profile_text.bbox(text)

        x=(bounds[2]-bounds[0]) if bounds else 0

        self.profile_text.create_text(x,y,text=name,anchor='w',fill='#d6ad52',font=font)



    def _color_profile_popup(self):

        if self.closed:return

        try:

            popup=self.choice.tk.call('ttk::combobox::PopdownWindow',str(self.choice))

            listing=str(popup)+'.f.l'

            # Keep slot numbers legible in the native selection list.

            for i in range(len(self.slots)):

                self.choice.tk.call(listing,'itemconfigure',i,'-foreground','#eee9df',

                                    '-selectforeground','#eee9df')

        except TclError:pass



    def render(self):

        if self.closed:return

        blocked=self.busy or self.app._closing or bool(getattr(getattr(self.app,'studio_settings',None),'busy',False))

        missing=self.connection_missing()

        if missing and not self.busy:self._show_disconnected()

        self.choice.configure(state='disabled' if blocked or self.app.engine else 'readonly')

        index=self.choice.current()

        selected_saved=0<=index<len(self.slots) and self.slots[index].state=='saved'

        # With no loadable selection the same button performs read-only discovery.

        allowed=not blocked and (not selected_saved or not self.app.engine)

        self.apply.configure(state='normal' if allowed else 'disabled',

                             style='Accent.TButton' if missing else 'TButton')

        active=(self.current_profile is not None and

                (self.current_profile==(self.slot_paths[index],self.slots[index].index) if 0<=index<len(self.slots)

                 else self.choice.get()==self._current_profile_display()))

        self.choice.configure(style='TCombobox')

        self.profile_caption.configure(text=tr(_ui_tr('현재 프로필:')) if active else tr(_ui_tr('슬롯 목록')),

                                       foreground='#eee9df' if active else '#aaa393')

        if active:

            name=self.current_profile_name

            display=self.choice.get()

            prefix=display[:-len(name)] if name and display.endswith(name) else ''

            value=(prefix,name)

            if value!=self._profile_display:

                self._profile_display=value;self._draw_profile_text()

        else:

            self._profile_display=None;self.profile_text.place_forget()



    def _show_disconnected(self):

        # Invalidate stale UI entries only after a confirmed absence. Preserve

        # the selected identity/binding so reconnect cannot choose another Pico.

        if not self.slots and self.current_profile is None and self.choice.get()==tr(_ui_tr('연결 없음')):return

        self.paths=[];self.slots=[];self.slot_paths=[];self.slot_labels=[]

        self.current_profile=None;self.current_profile_name=None

        self.observed_profile=None;self.auto_haptics_mode=None

        self.catalog_invalid=True;self.last_profile_check=-1e9

        self.choice.configure(values=());self.choice.set(tr(_ui_tr('연결 없음')))



    def task(self,kind,operation,allow_running=False):

        if power_blocked(self.app):return

        if self.closed or self.busy or self.app._closing:return

        if getattr(getattr(self.app,'studio_settings',None),'busy',False):return

        if self.app.engine and not (allow_running and kind=='discover'):return

        self.operation=kind;self.busy=True;self.render();self.app.last_render=None;self.app.render()

        def worker():

            try:self.results.put((kind,operation(),None))

            except Exception as exc:self.results.put((kind,None,str(exc)))

        start_thread(threading.Thread(target=worker,daemon=True))

        self.poll_id=self.app.root.after(80,self.poll)



    def check_before_start(self,on_ready):

        if power_blocked(self.app):return

        if self.closed or self.app._closing or self.app._close_requested or self.app.engine:return

        if self._start_callback is not None:return

        self._start_callback=on_ready

        # Auto-start can arrive while startup discovery is in flight. Queue

        # one fresh check after that task, instead of dropping the start request.

        if not self.busy:self._begin_start_check()



    def _begin_start_check(self):

        if self._start_callback is None or self.busy:return

        if self.closed or self.app._closing or self.app._close_requested or self.app.engine:

            self._start_callback=None;return

        self._active_check_generation=self.app.run_intent.generation if hasattr(self.app,'run_intent') else None

        preferred=self.selected[0] if self.selected else self.profile_path

        def read_current():

            error=None

            for delay in (0,.35,.8):

                if self._cancel.wait(delay):raise RuntimeError('Studio check cancelled')

                try:

                    candidates=devices()

                    identity=self.binding.snapshot()

                    serial=self.device_serials.get(preferred) or identity.serial

                    target=(self.binding.resolve_hid(candidates) if identity.hid_path is not None else

                            resolve_hid(candidates,preferred,serial,identity.container_id,

                                        allow_unique=preferred is None))

                    path=target['path'] if target else None

                    if path is None:

                        raise RuntimeError(tr(_ui_tr('Studio 대상 장치를 확인할 수 없습니다.')))

                    profile=run_device(path,action='read_profile_state')

                    if profile.get('auto_haptics_enable') not in (0,1,2):

                        raise RuntimeError('Studio autohaptics state unavailable')

                    profile=dict(profile,device_serial=target.get('serial_number'),device_row=target)

                    return path,profile

                except Exception as exc:error=exc

            raise error

        self.task('check_start',read_current)



    def _finish_start_check(self,result,error):

        generation=getattr(self,'_active_check_generation',None)

        if generation is not None and hasattr(self.app,'run_intent') and generation!=self.app.run_intent.generation:

            if self._start_callback is not None and self.app.run_intent.requested:self._begin_start_check()

            else:self._start_callback=None

            return

        callback,self._start_callback=self._start_callback,None

        if callback is None or self.closed or self.app._closing or self.app._close_requested:return

        if error:

            # Unknown is neither OFF nor permission to start using cached data.

            if hasattr(self.app,'run_intent'):self.app.run_intent.stop('start_error')

            self._status(tr(_ui_tr('Studio 응답 확인 실패 · '))+error)

        else:

            path,profile=result

            self._observe_profile(path,profile)

            self._sync_current_profile(path,profile)

            if not self.enforce_haptics_policy():callback()

        self.render();self.app.last_render=None;self.app.render()



    def _status(self,message):

        self._last_status=message

        self.app.status.set(message)



    @property

    def haptics_blocked(self):

        return self.auto_haptics_mode==0



    @property

    def haptics_notice(self):

        return tr(AUTOHAPTICS_OFF_MESSAGE)



    def _observe_profile(self,path,profile):

        # An unreadable response never invents OFF and never unlocks a known OFF.

        if not profile or profile.get('auto_haptics_enable') not in (0,1,2):return

        self.controller_connected=True

        old=self.observed_profile

        self.observed_profile={k:profile.get(k) for k in ('index','name','edited','auto_haptics_enable')}
        if profile['auto_haptics_enable']==1:
            self.observed_profile.update({key:profile[key] for key in ('mix_native_level','ah_dsp_source') if key in profile})
        if getattr(self.app,'engine',None):
            self.app.engine.front_only=self.native_mix_front_only()

        if old is not None and old!=self.observed_profile:self.catalog_invalid=True

        self.last_profile_check=time.monotonic()

        device_row=profile.get('device_row')

        if device_row and 'vendor_id' in device_row:

            self.xbox_hid_path=path if device_row['vendor_id']==0x1209 else None

        self.binding.bind_hid(profile.get('device_row') or dict(path=path,serial_number=profile.get('device_serial') or self.device_serials.get(path)))

        self.auto_haptics_mode=profile['auto_haptics_enable'];self.profile_path=path

        if profile.get('device_serial'):self.device_serials[path]=profile['device_serial']

        idle=getattr(self.app,'idle_presence',None)

        if idle is not None:

            if idle.absent:self.app.battery.next_check=0.

            idle.arm()

            if not self.haptics_blocked and self.app.status.get()==tr(_ui_tr('연결된 듀얼센스가 없습니다.')):

                self._status(tr(_ui_tr('Studio 연결 확인 완료')))

        if not self.haptics_blocked and self.app._stop_message==self.haptics_notice:

            self.app._stop_message=tr(_ui_tr('정지'))

        # A verified settings read also recovers an earlier startup/profile read

        # failure. Keep unrelated process/audio errors and Auto Haptics Off intact.

        failure_prefix=tr(_ui_tr('Studio 응답 확인 실패 · '))

        if (self.app._stop_message or '').startswith(failure_prefix):

            self.app._stop_message=self.haptics_notice if self.haptics_blocked else tr(_ui_tr('정지'))

        if self.app.status.get().startswith(failure_prefix):

            self._discovery_status(tr(_ui_tr('Studio 연결 확인 완료')))



    def native_mix_front_only(self):
        profile=self.observed_profile or {}
        return profile.get('auto_haptics_enable')==1 and (profile.get('mix_native_level') or 0)>0

    def native_mix_conflict(self):
        return self.native_mix_front_only() and self.observed_profile.get('ah_dsp_source')==1

    def _current_profile_display(self):

        if self.current_profile is None:return ''

        index=self.current_profile[1]

        return (f'{index+1:02d} · ' if index is not None else '')+(self.current_profile_name or '')



    def _sync_current_profile(self,path,profile):

        if not profile:return

        self.profile_path=path

        index=profile.get('index')

        self.selected=(path,index) if index is not None else None

        self.current_profile=(path,index)

        name=profile.get('name') or tr(_ui_tr('미저장 설정'))

        self.current_profile_name=name

        if len(self.slot_labels)!=len(self.slots):self.slot_labels=list(self.choice.cget('values'))

        labels=list(self.slot_labels)

        for position,slot in enumerate(self.slots):

            if self.slot_paths[position]==path and slot.index==index:

                # Preserve the slot number and draw only the name in gold.

                labels[position]=(f'{index+1:02d} · ' if index is not None else '')+name

                self.choice.configure(values=labels)

                self.choice.current(position)

                return

        # A successful start check may precede the first complete slot catalog.

        self.choice.set(self._current_profile_display())



    def enforce_haptics_policy(self):

        if not self.haptics_blocked:return False

        if hasattr(self.app,'run_intent'):self.app.run_intent.stop('profile_off')

        if self.app.engine:self.app.stop(message=self.haptics_notice,reason='profile_off')

        self._status(self.haptics_notice)

        return True



    def _discovery_status(self,message):

        if self.haptics_blocked:return

        # Do not clear a newer process/audio error while completing a HID read.

        current=self.app.status.get()

        owned=(self._last_status is not None and current==self._last_status)

        legacy=current.startswith(tr(_ui_tr('Studio 응답 확인 실패 · ')))

        process_hint=current==getattr(self.app,'_process_hint_message',None)

        if owned or legacy or process_hint or current==tr(_ui_tr('정지')):

            if self.app.engine and not self.app._stopping:

                self._status(tr(self.app.engine.status))

            else:

                self._status(message)

                update_hint=getattr(self.app,'_update_process_selection_status',None)

                if update_hint and message in (tr(_ui_tr('Studio 프로필 조회 완료')),tr(_ui_tr('Studio 연결 확인 완료'))):

                    update_hint(base=message)



    def recover_battery_connection(self,monitor):

        """One read-only recovery after a new battery/active-device observation.



        No new poller. Defer while local edits or other HID work are in flight.

        A cached percentage never authorizes profile activation or engine start.

        """

        device=getattr(monitor,'device',None)

        if monitor.state!='ready' or monitor.value is None or not device:

            self._battery_ready_key=None;self._battery_recovery_pending=None

            return

        key=(monitor.generation,device['path'],device.get('serial_number'))

        missing=self.current_profile is None or self.connection_missing()

        if key!=self._battery_ready_key:

            self._battery_ready_key=key

            self._battery_recovery_pending=dict(device) if missing else None

        target=self._battery_recovery_pending

        if not target:return

        if not missing:

            self._battery_recovery_pending=None;return

        app=self.app;editor=getattr(app,'studio_settings',None)

        if (self.closed or app._closing or app._close_requested or app._stopping

                or app.engine is not None or self.busy or monitor.busy):return

        if editor is not None:

            macro=getattr(editor,'macro_editor',None);doc=getattr(editor,'doc',None)

            if (editor.busy or getattr(editor,'reconnect_wait',False)

                    or macro is not None and not macro.closed

                    or doc is not None and (doc.dirty or doc.unsaved or doc.macros_pending_flash)):return

        identity=self.binding.snapshot()

        if identity.hid_path is not None or identity.serial or identity.container_id:

            if self.binding.resolve_hid([target]) is None:

                self._battery_recovery_pending=None;return

        elif self.selected is not None:

            path=self.selected[0]

            if resolve_hid([target],path,self.device_serials.get(path)) is None:

                self._battery_recovery_pending=None;return

        self._battery_recovery_pending=None

        self.discover(refresh=True,target_device=target)



    def discover(self,allow_running=False,refresh=False,after_start=False,target_device=None):

        if self.closed or self.app._closing:return

        if after_start and time.monotonic()-self.last_profile_check<5:return

        if self.app.engine and not allow_running:return

        # Start already validated the current profile. Reuse a recent catalog;

        # the explicit Load/Read action still forces a read of external changes.

        if (allow_running and not refresh and self.slots

                and self.profile_path in self.slot_paths

                and time.monotonic()-self.last_read<30 and not self.catalog_invalid):return

        if self.startup_id is not None:

            self.app.root.after_cancel(self.startup_id);self.startup_id=None

        # The in-flight read also satisfies a simultaneous launch/start request.

        if self.busy:return

        if not self.current_profile:

            self.choice.set(tr(_ui_tr('불러오는 중…')))

        self._discovery_status(tr(_ui_tr('Studio 연결 확인 중…')))

        def read():

            # USB enumeration can precede the Studio feature endpoint becoming

            # ready. Re-enumerate and reopen on each bounded, read-only retry.

            found=[];errors=[]

            for delay in (0,.35,.8):

                if self._cancel.wait(delay):return [],[]

                found=[];errors=[]

                try:candidates=devices()

                except Exception as exc:

                    candidates=[];errors.append(str(exc))

                if target_device is not None:

                    identity=self.binding.snapshot()

                    target=(self.binding.resolve_hid(candidates) if identity.hid_path is not None or identity.serial or identity.container_id

                            else resolve_hid(candidates,target_device['path'],target_device.get('serial_number'),target_device.get('container_id')))

                    candidates=[target] if target else []

                for device in candidates:

                    if self._cancel.is_set():return [],[]

                    path=device['path']

                    try:

                        slots=run_device(path)

                        if not any(slot.state!='unavailable' for slot in slots):

                            errors.append(tr(_ui_tr('Studio 프로필 응답 준비 중')));continue

                        try:profile=run_device(path,action='read_profile_state')

                        except Exception:

                            # Keep the slot list usable, but treat AH as unknown.

                            try:profile=run_device(path,action='read_profile')

                            except Exception:profile=None

                        found.append((device,slots,profile))

                    except Exception as exc:errors.append(str(exc))

                if found:break

            return found,errors

        self.task('discover',read,allow_running=allow_running)



    def activate(self,confirmed=False):

        if power_blocked(self.app):return

        if self.closed or self.busy or self.app._closing:return

        if bool(getattr(getattr(self.app,'studio_settings',None),'busy',False)):return

        if self.connection_missing():

            self.discover(allow_running=True,refresh=True);return

        index=self.choice.current()

        if not (0<=index<len(self.slots) and self.slots[index].state=='saved'):

            self.discover(allow_running=True,refresh=True);return

        if self.app.engine:return

        editor=getattr(self.app,'studio_settings',None)

        if editor is not None and not confirmed and (editor.profile_changes_pending() or editor.shared_changes_pending()):

            wanted_path=self.slot_paths[index];wanted_slot=self.slots[index].index

            was_bound=wanted_path==self.binding.snapshot().hid_path

            def continue_selection():

                # Saving the old profile updates the current-profile dropdown.

                # Restore the requested destination rather than activating it.

                path=self.binding.snapshot().hid_path if was_bound else wanted_path

                position=next((i for i,s in enumerate(self.slots) if s.index==wanted_slot and self.slot_paths[i]==path),None)

                if position is None:

                    self._status(tr(_ui_tr('프로필 선택')));return

                self.choice.current(position);self.activate(confirmed=True)

            editor.request_profile_switch(continue_selection);return

        path=self.slot_paths[index];slot=self.slots[index]

        self.selected=(path,slot.index)

        editor=getattr(self.app,'studio_settings',None)

        if editor is not None:editor.invalidate_profile()

        def apply_selected():

            # Activation is sent once. Only the following state read may fail.

            original_devices=devices()

            original=next((item for item in original_devices if item['path']==path),{})

            identity=self.binding.snapshot()

            serial=original.get('serial_number') or self.device_serials.get(path)

            if path==identity.hid_path:

                serial=serial or identity.serial

            container=original.get('container_id')

            if not serial and not container and path!=identity.hid_path:

                from windows_device_identity import hid_container

                container=hid_container(path)

            self.binding.expect_reconnect()

            try:result=run_device(path,slot.index)

            except (TimeoutError,OSError):

                # A lost activation reply is ambiguous: verify the desired state

                # without repeating activation or issuing an unconfirmed reset.

                result=dict(slot=slot,reconnect=False,deferred=False,activation_unconfirmed=True)

            result.update(path=path,old_path=path,profile=None,verified=False,device_serial=serial)

            if result['reconnect']:

                try:run_device(path,action='reconnect_usb')

                except Exception:

                    # Windows may close the handle during the successful write.

                    # Verify by reading, rather than sending a second reset.

                    pass

            for delay in ((.25,.35,.55,.8,1.,1.2,1.5,1.8) if result['reconnect'] or result.get('activation_unconfirmed') else (0,.35,.8)):

                if self._cancel.wait(delay):break

                try:

                    candidates=devices()

                    if path==identity.hid_path:

                        target=self.binding.resolve_hid(candidates)

                    else:

                        if container and not serial:

                            from windows_device_identity import hid_container

                            candidates=[dict(row,container_id=row.get('container_id') or hid_container(row['path']))

                                        for row in candidates]

                        target=resolve_hid(candidates,path,serial,container)

                    if target is None:continue

                    profile=run_device(target['path'],action='read_profile_state')

                    if profile.get('index')!=slot.index or profile.get('edited') is True:continue

                    if slot.name and profile.get('name')!=slot.name:continue

                    if (result['reconnect'] or result.get('activation_unconfirmed')) and target.get('vendor_id') in (0x054c,0x1209):

                        from studio_settings_protocol import USBModeUnsupported

                        try:mode=run_device(target['path'],action='read_usb_mode')

                        except USBModeUnsupported:

                            if target.get('vendor_id')==0x1209 or original.get('vendor_id')==0x1209:

                                continue

                            mode=0

                        if (mode==1)!=(target.get('vendor_id')==0x1209):

                            continue

                    profile=dict(profile,device_row=target,device_serial=target.get('serial_number'))

                    result.update(path=target['path'],profile=profile,verified=True,

                                  device_serial=target.get('serial_number') or serial)

                    break

                except Exception:continue

            return result

        self.task('activate',apply_selected)



    def poll(self):

        self.poll_id=None

        if self.closed:return

        try:kind,result,error=self.results.get_nowait()

        except queue.Empty:

            self.poll_id=self.app.root.after(80,self.poll);return

        self.busy=False;self.operation=None

        if kind=='check_start':

            self._finish_start_check(result,error)

            return

        if error:

            self.catalog_invalid=True

            if not self.current_profile:self.choice.set(tr(_ui_tr('조회 실패')))

            self._status(tr(_ui_tr('Studio 응답 확인 실패 · '))+error)

        elif kind=='discover':

            self.last_read=time.monotonic();found,errors=result;labels=[];active=None;profile_active=None

            if not found:

                self.catalog_invalid=True

                if not errors and not self._cancel.is_set():self.controller_connected=False

                self._status(tr(_ui_tr('Studio 응답 확인 실패 · '))+(errors[0] if errors else tr(_ui_tr('연결된 듀얼센스가 없습니다.'))))

                self.render();self.app.last_render=None;self.app.render()

                if self._start_callback is not None:self._begin_start_check()

                return

            self.slots=[];self.slot_paths=[];self.catalog_invalid=False

            self.paths=[device['path'] for device,_,_ in found]

            for device_index,(device,slots,profile) in enumerate(found,1):

                if device.get('serial_number'):self.device_serials[device['path']]=device['serial_number']

                prefix=''

                if len(found)>1:

                    serial=device.get('serial_number') or 'USB'

                    prefix=f'{device_index:02d} · '+str(serial)[-8:]+' · '

                for slot in slots:

                    i=len(labels);self.slots.append(slot);self.slot_paths.append(device['path'])

                    name=(slot.name or tr(_ui_tr('이름 없음'))) if slot.state=='saved' else tr(_ui_tr('빈 슬롯')) if slot.state=='empty' else tr(_ui_tr('사용 불가'))

                    labels.append(prefix+f'{slot.index+1:02d} · '+name)

                    if self.selected==(device['path'],slot.index):active=i

                    if len(found)==1 and profile and profile['index']==slot.index:profile_active=i

            self.slot_labels=list(labels)

            self.choice.configure(values=labels)

            if active is None:active=profile_active

            if active is not None:

                self.choice.current(active)

                self.selected=(self.slot_paths[active],self.slots[active].index)

            else:

                self.selected=None

                self.choice.set(tr(_ui_tr('프로필 선택')) if labels else tr(_ui_tr('연결된 프로필 없음')))

            target=self.selected[0] if self.selected else self.paths[0] if len(self.paths)==1 else None

            for device,slots,profile in found:

                if device['path']==target:

                    self._observe_profile(target,dict(profile,device_row=device,device_serial=device.get('serial_number')))

                    self._sync_current_profile(target,profile)

            if found:

                self.catalog_invalid=False

                self._discovery_status(tr(_ui_tr('Studio 프로필 조회 완료')))

            elif errors:self._status(tr(_ui_tr('Studio 응답 확인 실패 · '))+errors[0])

            else:self._discovery_status(tr(_ui_tr('연결된 듀얼센스가 없습니다.')))

        else:

            old_path=result.get('old_path');new_path=result.get('path')

            editor=getattr(self.app,'studio_settings',None)

            if editor is not None:editor.invalidate_profile()

            if result.get('device_serial'):self.device_serials[new_path]=result['device_serial']

            if result.get('verified') and old_path!=new_path:

                self.slot_paths=[new_path if path==old_path else path for path in self.slot_paths]

                self.paths=[new_path if path==old_path else path for path in self.paths]

            self._observe_profile(result.get('path'),result.get('profile'))

            self._sync_current_profile(result.get('path'),result.get('profile'))

            slot=result['slot']

            if result.get('verified'):

                self._status(tr(_ui_tr('슬롯 적용 완료'))+' · '+slot.label())

                if result['reconnect'] or old_path!=new_path:self.app.refresh_devices()

                if editor is not None and self.app.selected_tab==2:

                    editor.begin_entry()

                    # Loading a slot changes live settings, not the saved slot

                    # catalog. Refresh current values without rereading 32 slots.

                    editor.entry_attempts.add('slots')

            else:

                self.catalog_invalid=True

                self._status(tr(_ui_tr('프로필 적용 후 상태를 확인하지 못했습니다. 연결을 확인한 후 다시 조회하세요.')))

                self.last_read=-1e9

            if result.get('verified') and result['deferred']:self._status(self.app.status.get()+tr(_ui_tr(' · 유지 여부는 재연결 후 확인')))

        self.enforce_haptics_policy()

        self.render();self.app.last_render=None;self.app.render()

        if self._start_callback is not None:self._begin_start_check()



    def close(self):

        self.closed=True

        self._start_callback=None

        self._cancel.set()

        for name in ('poll_id','startup_id'):

            job=getattr(self,name)

            if job:

                self.app.root.after_cancel(job);setattr(self,name,None)



    def connection_missing(self):

        return (self.controller_connected is False

                or bool(getattr(getattr(self.app,'idle_presence',None),'absent',False))

                or self.app.engine is not None and bool(getattr(getattr(self.app,'controller_presence',None),'disconnected',False)))

