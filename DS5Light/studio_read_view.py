"""Refresh Studio reads without destroying the visible option controls."""
from studio_i18n import text as _ui_tr
import copy
import tkinter as tk
from tkinter import ttk
from studio_fields import FIELDS
from studio_help import options
from studio_scope import trigger_display

READ_JOBS=('read','entry_read','slots','macros')

class StableReadView:
    def read_view_lock(self):
        if not self.built:return
        saved=getattr(self,'_read_view_states',None)
        if saved is None:self._read_view_states=saved={}
        def walk(parent):
            for child in parent.winfo_children():
                if hasattr(child,'set_enabled'):
                    if child not in saved:saved[child]=('enabled',child.enabled)
                    child.set_enabled(False)
                elif hasattr(child,'enabled') and hasattr(child,'draw'):
                    if child not in saved:saved[child]=('slider',child.enabled)
                    if child.enabled:
                        child.enabled=False;child.configure(takefocus=0);child.draw()
                elif isinstance(child,(ttk.Entry,ttk.Combobox,ttk.Button,tk.Button)):
                    if child not in saved:saved[child]=('state',str(child.cget('state')))
                    child.configure(state='disabled')
                # ControllerChoice has its own enabled state and label bindings.
                elif hasattr(child,'expanded') and hasattr(child,'enabled'):
                    if child not in saved:saved[child]=('state',str(child.cget('state')))
                    child.configure(state='disabled')
                walk(child)
        walk(self.body)

    def read_view_unlock(self):
        saved=getattr(self,'_read_view_states',{})
        self._read_view_states={}
        for child,(kind,value) in saved.items():
            if not child.winfo_exists():continue
            if kind=='enabled':child.set_enabled(value)
            elif kind=='slider':
                if child.enabled!=value:
                    child.enabled=value;child.configure(takefocus=int(value));child.draw()
            else:child.configure(state=value)

    def refresh_read_values(self,keys=None):
        self._syncing_fields=True
        try:
            for key,view in getattr(self,'field_views',{}).items():
                if keys is not None and key not in keys:continue
                title,controls,bits=view
                f=getattr(self,'_display_fields',{}).get(key,FIELDS[key]);value=self.doc.values.get(key);variable=self.vars[key]
                if f[4]=='bool':text=bool(value)
                elif f[4]=='select':text=dict(options(f)).get(value,_ui_tr('밝기 선택') if key=='player_led_bright' and value==3 else _ui_tr('미지원') if value is None else str(value))
                elif f[4]=='color':text='' if value is None else str(value)
                else:text='' if value is None else format(value,'.5g')
                if key not in self.invalid and variable.get()!=text:variable.set(text)
                for bitvar,index in bits:
                    selected=bool(int(value or 0)&(1<<index))
                    if bitvar.get()!=selected:bitvar.set(selected)
                if key in ('trigger_reduce','rumble_gain') and key not in self.invalid:
                    entry=controls[0]
                    display='' if value is None else f'{trigger_display(value) if key=="trigger_reduce" else value/100:g}'
                    name=str(entry.cget('textvariable'))
                    if str(self.parent.getvar(name))!=display:self.parent.setvar(name,display)
                valid=key in self.doc.values and self.enabled_for(key)
                enabled=valid and not self.busy
                for control in controls:
                    if hasattr(control,'set_enabled'):control.set_enabled(enabled)
                    elif hasattr(control,'enabled') and hasattr(control,'draw'):
                        if control.enabled!=enabled:
                            control.enabled=enabled;control.configure(takefocus=int(enabled));control.draw()
                    else:
                        state=('readonly' if f[4]=='select' else 'normal') if enabled else 'disabled'
                        if str(control.cget('state'))!=state:control.configure(state=state)
                    if hasattr(control,'_paint_colour'):control._paint_colour()
                for child in title.winfo_children():
                    if isinstance(child,tk.Label):
                        if child.cget('text')==_ui_tr('오디오햅틱 끔에서만 작동'):continue
                        colour='#eee9df' if valid else '#aaa393'
                        if str(child.cget('fg'))!=colour:child.configure(fg=colour)
        finally:self._syncing_fields=False
        self.refresh_lighting()
        self.refresh_option_groups()
        if keys is None:self.refresh_read_extras()
        self.update_state()

    def extras_signature(self):
        common=(self.category,self.loaded,self.write_ready,self.pico_recognized,self.path)
        if self.category==4:
            return common+(tuple((key,tuple(record)) for key,record in self.doc.macros.items()),self.doc.values.get('macro_disable'),getattr(self,'macro_layer',False))
        if self.category==0:return (0,self.standby_value(),self.standby_value('dock_policy'),self.busy)
        if self.category==5:return common+(tuple(sorted((self.profile_stamp or {}).items())),tuple((slot.index,slot.state,slot.name) for slot in self.slots))
        if self.category==2:
            from studio_scope import TRIGGER_FIELDS
            return common + (self.busy, tuple((k,self.doc.values.get(k)) for k in sorted(TRIGGER_FIELDS)))
        if self.category==3:return common
        return (self.category,)

    def refresh_read_extras(self):
        box=getattr(self,'_extra_body',None)
        if box is None or not box.winfo_exists():return
        signature=self.extras_signature()
        if signature==getattr(self,'_extra_signature',None):return
        if self.category == 2:
            from studio_scope import TRIGGER_FIELDS
            for key in TRIGGER_FIELDS:
                self.field_views.pop(key, None)
                self.vars.pop(key, None)
                self.range_controls.pop(key, None)
        for child in box.winfo_children():child.destroy()
        self.tips=[tip for tip in self.tips if tip.widget.winfo_exists()]
        body=self.body;self.body=box
        try:
            if self.category==0:self.render_standby_policy()
            elif self.category==2:self.render_construction()
            elif self.category==4:self.render_macros();self.render_macro_tools()
            elif self.category==5:self.render_slots();self.render_files();self.render_recommended_presets()
            elif self.category==3:self.render_calibration()
        finally:self.body=body
        self._extra_signature=signature
        self.sync_scrollregion()
