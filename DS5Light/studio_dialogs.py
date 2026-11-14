"""Small themed confirmation dialog; no platform message box colors."""
from studio_i18n import text as _ui_tr
import tkinter as tk
from tkinter import ttk
from localization import tr
from ui_dpi import fit_window,scale_styles,install_dpi

def _theme(dialog):
    import sys
    main=sys.modules.get('__main__')
    apply=getattr(main,'apply_windows_titlebar_theme',None)
    if apply is None:
        from app import apply_windows_titlebar_theme as apply
    apply(dialog)

def _styles(parent):
    style=ttk.Style(parent)
    try:style.layout('Dialog.TButton',style.layout('Filter.TButton'))
    except tk.TclError:pass
    style.configure('Dialog.TButton',background='#242321',foreground='#eee9df',padding=(12,6))
    style.configure('Accent.Dialog.TButton',background='#d6ad52',foreground='#211a0d',padding=(12,6))
    style.map('Accent.Dialog.TButton',background=[('active','#e7c875')])
    scale_styles(parent._root(),style,('Dialog.TButton','Accent.Dialog.TButton'))

def _show(dialog,owner,focus):
    install_dpi(owner._root()).watch_window(dialog)
    dialog.bind('<Map>',lambda e:dialog.after_idle(lambda:_theme(dialog)) if e.widget is dialog else None,add='+')
    dialog.update_idletasks();_theme(dialog);w,h=dialog.winfo_reqwidth(),dialog.winfo_reqheight()
    x=owner.winfo_rootx()+(owner.winfo_width()-w)//2;y=owner.winfo_rooty()+(owner.winfo_height()-h)//2
    previous=owner.grab_current()
    fit_window(dialog,w,h,position=(x,y),reference=owner)
    dialog.deiconify();dialog.grab_set();focus.focus_set();dialog.wait_window()
    if previous is not None:
        try:
            if previous.winfo_exists():previous.grab_set()
        except tk.TclError:pass

def _input(parent,title,prompt,initial='',max_bytes=None):
    owner=(parent or tk._default_root).winfo_toplevel();dialog=tk.Toplevel(owner);dialog.withdraw();dialog.title(title);dialog.configure(bg='#151515');dialog.transient(owner);dialog.resizable(False,False);_styles(dialog)
    result=[None]
    def finish(value=None):result[0]=value;dialog.destroy()
    box=tk.Frame(dialog,bg='#151515',padx=24,pady=22);box.pack(fill='both',expand=True)
    tk.Label(box,text=title,bg='#151515',fg='#d6ad52',font=(_ui_tr('맑은 고딕'),12,'bold'),anchor='w').pack(fill='x',pady=(0,12))
    tk.Label(box,text=prompt,bg='#151515',fg='#aaa393',wraplength=400,justify='left',anchor='w').pack(fill='x',pady=(0,10))
    value=tk.StringVar(value=initial);entry=ttk.Entry(box,textvariable=value,style='Studio.TEntry',width=34);entry.pack(fill='x')
    hint=tk.Label(box,text='',bg='#151515',fg='#cf9292',wraplength=400,justify='left',anchor='w');hint.pack(fill='x',pady=(8,0))
    def accept(event=None):
        name=value.get()
        if '\x00' in name or (max_bytes is not None and len(name.encode('utf-8'))>max_bytes):
            hint.configure(text=tr(_ui_tr('프로필 이름은 UTF-8 16바이트 이내로 입력하세요.')) if max_bytes else tr(_ui_tr('이름에 사용할 수 없는 문자가 있습니다.')));return
        finish(name)
    actions=tk.Frame(box,bg='#151515');actions.pack(pady=(16,0))
    ttk.Button(actions,text=tr(_ui_tr('취소')),width=12,style='Dialog.TButton',command=finish).pack(side='left',padx=(0,8))
    ttk.Button(actions,text=tr(_ui_tr('저장')),width=12,style='Accent.Dialog.TButton',command=accept).pack(side='left')
    dialog.protocol('WM_DELETE_WINDOW',finish);dialog.bind('<Escape>',lambda e:finish());dialog.bind('<Return>',accept);entry.selection_range(0,'end')
    _show(dialog,owner,entry);return result[0]

def profile_name(parent,initial=''):
    return _input(parent,tr(_ui_tr('프로필 이름')),tr(_ui_tr('현재 적용된 값을 이 슬롯에 저장합니다.\n이름은 UTF-8 16바이트 이내로 입력하세요.')),initial,max_bytes=16)

def confirm_delete(parent):
    return _confirm(parent,_ui_tr('매핑 삭제'),_ui_tr('매핑을 삭제할까요?'),
                    _ui_tr('이 매핑을 사용하는 모든 프로필에 영향을 줍니다.\n확인하면 삭제 내용과 다른 미저장 공용 매핑을 Pico에 자동 저장합니다.'),_ui_tr('삭제'))

def confirm_bootloader(parent):
    return _confirm(parent,_ui_tr('Pico 부트로더'),_ui_tr('부트로더로 재시작할까요?'),
                    _ui_tr('Pico를 UF2 설치 모드(RPI-RP2)로 재시작합니다.\n듀얼센스 연결이 해제됩니다.'),_ui_tr('재시작'))

def profile_switch(parent,*,profile,shared,profile_applied,shared_applied):
    owner=parent.winfo_toplevel();dialog=tk.Toplevel(owner);dialog.withdraw()
    dialog.title(_ui_tr('프로필 전환'));dialog.configure(bg='#151515');dialog.transient(owner);dialog.resizable(False,False);_styles(dialog)
    result=[None]
    def finish(value=None):result[0]=value;dialog.destroy()
    box=tk.Frame(dialog,bg='#151515',padx=24,pady=22);box.pack()
    tk.Label(box,text=_ui_tr('저장하지 않은 변경이 있습니다.'),bg='#151515',fg='#d6ad52',font=(_ui_tr('맑은 고딕'),12,'bold')).pack(anchor='w')
    lines=[]
    if profile:lines.append(_ui_tr('현재 프로필 설정')+
                            (_ui_tr(' · 임시 적용값 포함') if profile_applied else ''))
    if shared:lines.append(_ui_tr('Pico 공용 매핑·매크로 · 모든 프로필에 적용')+
                           (_ui_tr(' · 임시 적용값 포함') if shared_applied else ''))
    tk.Label(box,text='\n'.join(lines),bg='#151515',fg='#eee9df',wraplength=420,justify='left').pack(anchor='w',pady=(12,20))
    actions=tk.Frame(box,bg='#151515');actions.pack()
    focus=None
    save_label=_ui_tr('프로필과 공용 매크로 저장 후 전환') if profile and shared else (
        _ui_tr('공용 매크로 저장 후 전환') if shared else _ui_tr('현재 프로필 저장 후 전환'))
    for caption,value in [(_ui_tr('취소'),None),(_ui_tr('변경 버리기'),'discard'),(save_label,'save')]:
        button=ttk.Button(actions,text=caption,style='Accent.Dialog.TButton' if value=='save' else 'Dialog.TButton',command=lambda v=value:finish(v))
        if value=='discard' and shared_applied:button.configure(state='disabled')
        button.pack(side='left',padx=4)
        if focus is None:focus=button
    dialog.protocol('WM_DELETE_WINDOW',finish);dialog.bind('<Escape>',lambda e:finish())
    _show(dialog,owner,focus);return result[0]

def _message(parent,title,heading,message,accept=_ui_tr('확인'),cancel=False,cancel_label=None):
    owner=(parent or tk._default_root).winfo_toplevel();dialog=tk.Toplevel(owner);dialog.withdraw();dialog.title(title);dialog.configure(bg='#151515');dialog.resizable(False,False);_styles(dialog)
    if owner.state() != 'withdrawn':dialog.transient(owner)
    result=[False]
    def finish(value=False):result[0]=value;dialog.destroy()
    box=tk.Frame(dialog,bg='#151515',padx=24,pady=22);box.pack(fill='both',expand=True)
    tk.Label(box,text=heading,bg='#151515',fg='#d6ad52',font=(_ui_tr('맑은 고딕'),12,'bold'),anchor='w',wraplength=420,justify='left').pack(fill='x',pady=(0,12))
    label=tk.Label(box,text=message,bg='#151515',fg='#eee9df',font=(_ui_tr('맑은 고딕'),10),wraplength=420,justify='left',anchor='w');label.pack(fill='x')
    dialog.update_idletasks()
    if label.winfo_reqheight()>max(140,dialog.winfo_screenheight()-260):
        label.destroy();area=tk.Frame(box,bg='#151515');area.pack(fill='both',expand=True)
        text=tk.Text(area,bg='#151515',fg='#eee9df',font=(_ui_tr('맑은 고딕'),10),wrap='word',width=48,height=max(5,min(18,(dialog.winfo_screenheight()-280)//22)),relief='flat',highlightthickness=0)
        scroll=ttk.Scrollbar(area,orient='vertical',command=text.yview);text.configure(yscrollcommand=scroll.set);text.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y');text.insert('1.0',message);text.configure(state='disabled')
    actions=tk.Frame(box,bg='#151515');actions.pack(pady=(20,0))
    if cancel:
        focus=ttk.Button(actions,text=tr(cancel_label or _ui_tr('취소')),width=12,style='Dialog.TButton',command=finish);focus.pack(side='left',padx=(0,8))
    button=ttk.Button(actions,text=tr(accept),width=12,style='Accent.Dialog.TButton',command=lambda:finish(True));button.pack(side='left')
    if not cancel:focus=button
    dialog.protocol('WM_DELETE_WINDOW',finish);dialog.bind('<Escape>',lambda e:finish())
    _show(dialog,owner,focus);return result[0]

def _confirm(parent,title,heading,message,accept):
    return _message(parent,title,heading,message,accept,cancel=True)

def confirm_macro_profile(parent,target,other_changes):
    name=target[1] or _ui_tr('이름 없음')
    message=_ui_tr('매핑 동작은 Pico에 저장되었습니다.\n현재 프로필: {0:02d} · {1}\n현재 프로필의 사용 체크와 설정을 저장하시겠습니까?').format(target[0]+1,name)
    if other_changes:message+='\n'+_ui_tr('함께 저장할 다른 프로필 설정 변경: {0}개').format(other_changes)
    return _message(parent,_ui_tr('매핑 프로필 저장'),_ui_tr('현재 프로필에 저장하시겠습니까?'),message,
                    _ui_tr('저장'),cancel=True,cancel_label=_ui_tr('나중에'))

class ThemedMessages:
    @staticmethod
    def askyesno(title,message,parent=None,**kwargs):
        return _message(parent,title,title,message,cancel=True)
    @staticmethod
    def showerror(title,message,parent=None,**kwargs):
        _message(parent,title,title,message);return 'ok'
    showwarning=showerror
    showinfo=showerror

class ThemedInput:
    @staticmethod
    def askstring(title,prompt,initialvalue='',parent=None,**kwargs):
        return _input(parent,title,prompt,initialvalue)

messagebox=ThemedMessages()
simpledialog=ThemedInput()
