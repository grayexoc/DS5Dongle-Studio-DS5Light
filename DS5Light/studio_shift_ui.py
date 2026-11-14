"""Inline, locally staged shift-key selection using the shared button palette."""
import tkinter as tk
import copy
from tkinter import ttk
from controller_glyphs import ControllerChoice
from studio_i18n import text as tr
from studio_shift import shift_key, set_shift_key
from studio_button_names import NAMES

CARD='#151515';MUTED='#aaa393'


class ShiftUI:
    def render_shift_controls(self,box):
        host=tk.Frame(box,bg=CARD);host.grid(row=6,column=0,columnspan=2,sticky='ew',pady=8)
        bar=tk.Frame(host,bg=CARD);bar.pack(fill='x')
        for value,title in [(False,tr('기본')),(True,tr('레이어'))]:
            ttk.Button(bar,text=title,command=lambda v=value:self.select_macro_layer(v),
                       style='Selected.Filter.TButton' if value==getattr(self,'macro_layer',False) else 'Filter.TButton').pack(side='left',padx=(0,5))
        ttk.Button(bar,text=tr('시프트 레이어키 지정'),command=self.open_shift_picker).pack(side='right')
        row=shift_key(self.doc.macros)
        bit=int.from_bytes(bytes(row[1][:4]),'little').bit_length()-1 if row else None
        self.shift_key_label=tk.Label(bar,text=NAMES[bit] if bit is not None and 0<=bit<23 else tr('없음'),bg=CARD,fg=MUTED)
        self.shift_key_label.pack(side='right',padx=(8,8))
        self.shift_editor=tk.Frame(host,bg=CARD)
        self.shift_selection=tk.StringVar(value=tr('없음'))
        self.shift_enabled=tk.BooleanVar()
        self.shift_choice=ControllerChoice(self.shift_editor,textvariable=self.shift_selection,values=[tr('없음')]+NAMES[:23])
        self.shift_choice.pack(fill='x',pady=(8,6))
        self.shift_choice.bind('<<ComboboxSelected>>',lambda _:self.shift_enabled.set(self.shift_selection.get() in NAMES))
        from studio_settings_ui import CircleCheck
        CircleCheck(self.shift_editor,text=tr('현재 프로필에서 사용'),variable=self.shift_enabled,command=lambda:None,background=CARD).pack(anchor='w')
        self.shift_notice=tk.StringVar(value=tr('누르는 동안 시프트 · 미지정 입력은 기본 매핑 상속 · 시프트키는 게임에서 숨김'))
        tk.Label(self.shift_editor,textvariable=self.shift_notice,bg=CARD,fg=MUTED,wraplength=420,justify='left').pack(anchor='w',pady=6)
        actions=tk.Frame(self.shift_editor,bg=CARD);actions.pack(anchor='w')
        ttk.Button(actions,text=tr('완료 · Pico 저장'),command=self.commit_shift_key).pack(side='left')
        ttk.Button(actions,text=tr('취소'),command=self.cancel_shift_key).pack(side='left',padx=8)

    def select_macro_layer(self,shifted):
        self.macro_layer=shifted
        self.render_fields()

    def open_shift_picker(self):
        if self.busy or not self.loaded or not self.write_ready or 'macro_disable' not in self.doc.values:return
        if not self.doc.macro_baseline:
            self.after_macro_read=self.open_shift_picker
            self.task('macros',lambda:self.with_client(lambda c:c.read_macros()));return
        if self.shift_editor.winfo_manager():
            self.cancel_shift_key();return
        row=shift_key(self.doc.macros)
        self.shift_stamp=copy.deepcopy(self.profile_stamp);self.shift_path=self.path
        bit=int.from_bytes(bytes(row[1][:4]),'little').bit_length()-1 if row else None
        self.shift_selection.set(NAMES[bit] if bit is not None and 0<=bit<23 else tr('없음'))
        self.shift_enabled.set(bool(row and not self.doc.values.get('macro_disable',0xffffffff)&(1<<row[0])))
        self.shift_editor.pack(fill='x',pady=(4,0))
        if not self.shift_choice.expanded:self.shift_choice.toggle()

    def cancel_shift_key(self):
        self.shift_choice.collapse()
        self.shift_editor.pack_forget()

    def commit_shift_key(self):
        if not self.macro_edit_ready():return
        if self.shift_stamp!=self.profile_stamp or self.shift_path!=self.path:
            self.shift_notice.set(tr('현재 프로필이 바뀌었습니다. 다시 읽어 주세요.'));return
        try:
            bit=NAMES.index(self.shift_selection.get()) if self.shift_selection.get() in NAMES else None
            records,mask=set_shift_key(self.doc.macros,int(self.doc.values.get('macro_disable',0xffffffff)),bit)
            row=shift_key(records)
            if row and not self.shift_enabled.get():mask|=1<<row[0]
            from studio_shift import validate_reserved_inputs
            validate_reserved_inputs(records,dict(self.doc.values,macro_disable=mask))
            self.doc.macros=records
            self.render_fields()
            self.save_macro_edits(copy.deepcopy(self.profile_stamp),mask=mask)
        except ValueError as exc:self.shift_notice.set(str(exc))
