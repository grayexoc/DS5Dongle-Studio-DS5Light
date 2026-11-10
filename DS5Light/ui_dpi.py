"""Window DPI and logical pixel helpers; no hooks, device I/O or polling loop."""
import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont
import weakref


def enable_dpi_awareness():
    if sys.platform != 'win32':return
    try:
        # Before Tk creates a window. Respect a manifest/host that already set it.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError,OSError):pass


def _window_dpi(window):
    if sys.platform != 'win32':return 96
    try:
        from ctypes import wintypes
        query=ctypes.windll.user32.GetDpiForWindow
        query.argtypes=[wintypes.HWND];query.restype=wintypes.UINT
        dpi=query(window.winfo_id())
        if dpi:return dpi
    except (AttributeError,OSError,tk.TclError):pass
    try:return max(96,round(window.winfo_fpixels('1i')))
    except tk.TclError:return 96


def ui_scale(widget):
    # Tk fonts/styles are shared by one interpreter: all its windows must agree.
    root=widget._root()
    scale=getattr(root,'_ui_scale',None)
    return _window_dpi(root)/96 if scale is None else scale


def px(widget,value):
    return round(float(value)*ui_scale(widget))


def work_area(window):
    if sys.platform=='win32':
        try:
            from ctypes import wintypes
            class MonitorInfo(ctypes.Structure):
                _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
            user=ctypes.windll.user32
            monitor=user.MonitorFromWindow
            monitor.argtypes=[wintypes.HWND,wintypes.DWORD];monitor.restype=wintypes.HANDLE
            query=user.GetMonitorInfoW
            query.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)];query.restype=wintypes.BOOL
            info=MonitorInfo();info.size=ctypes.sizeof(info)
            if query(monitor(window.winfo_id(),2),ctypes.byref(info)):
                r=info.work;return r.left,r.top,r.right,r.bottom
        except (AttributeError,OSError,tk.TclError):pass
    return 0,0,window.winfo_screenwidth(),window.winfo_screenheight()


def fit_window(window,width,height,*,logical=False,min_width=1,min_height=1,position=None,reference=None):
    left,top,right,bottom=work_area(reference if reference is not None else window)
    window._dpi_minimum=(min_width/ui_scale(window),min_height/ui_scale(window))
    max_width=max(1,right-left-px(window,24));max_height=max(1,bottom-top-px(window,48))
    if logical:width,height=px(window,width),px(window,height)
    minimum=(min(max_width,max(1,round(min_width))),min(max_height,max(1,round(min_height))))
    width=max(minimum[0],min(max_width,round(width)))
    height=max(minimum[1],min(max_height,round(height)))
    window.minsize(*minimum)
    geometry=f'{width}x{height}'
    if position is not None:
        x=max(left,min(right-width,round(position[0])))
        y=max(top,min(bottom-height-px(window,36),round(position[1])))
        # Leading + selects absolute coordinates, including negative monitors.
        geometry+=f'+{x}+{y}'
    window.geometry(geometry)


class DpiTracker:
    def __init__(self,root):
        self.root=root;self.windows=weakref.WeakKeyDictionary();self.styles={}
        self.watch_window(root)
        self._fonts(root._ui_scale)

    def _fonts(self,scale):
        # Tk point fonts already include DPI. Update their point conversion once.
        scaling=scale*96/72
        if abs(float(self.root.tk.call('tk','scaling'))-scaling)<.01:return
        self.root.tk.call('tk','scaling',scaling)
        for name in tkfont.names(self.root):
            font=tkfont.nametofont(name,self.root);size=font.cget('size')
            if size>0:font.configure(size=size)

    def watch_window(self,window):
        if window in self.windows:return
        window._ui_scale=_window_dpi(window)/96 if window is self.root else self.root._ui_scale
        self.windows[window]={'widgets':weakref.WeakKeyDictionary(),'job':None}
        window.bind('<Configure>',lambda e:self._schedule(window) if e.widget is window else None,add='+')
        window.bind('<Destroy>',lambda e:self._remove(window) if e.widget is window else None,add='+')

    def _remove(self,window):
        data=self.windows.pop(window,None)
        if data and data['job']:
            try:window.after_cancel(data['job'])
            except tk.TclError:pass

    def _schedule(self,window):
        data=self.windows.get(window)
        if data is None:return
        if data['job']:window.after_cancel(data['job'])
        data['job']=window.after(120,lambda:self._update(window))

    def _update(self,window):
        data=self.windows.get(window)
        if data is None or not window.winfo_exists():return
        data['job']=None
        scale=_window_dpi(self.root)/96;previous=self.root._ui_scale
        if abs(scale-previous)<.01:return
        self.root._ui_scale=scale
        self._fonts(scale)
        for style,name,values in self.styles.values():self._style(style,name,values,scale)
        for target,entry in list(self.windows.items()):
            if not target.winfo_exists():continue
            minimum=getattr(target,'_dpi_minimum',None)
            if minimum is None:minimum=tuple(v/previous for v in target.minsize())
            target._dpi_minimum=minimum;target._ui_scale=scale
            if target.state()=='normal':
                ratio=scale/previous
                fit_window(target,target.winfo_width()*ratio,target.winfo_height()*ratio,
                           min_width=minimum[0]*scale,min_height=minimum[1]*scale,
                           position=(target.winfo_x(),target.winfo_y()))
            for widget,reference in list(entry['widgets'].items()):
                callback=reference()
                if callback is not None and widget.winfo_exists():callback()

    def _style(self,style,name,values,scale):
        style.configure(name,**{key:tuple(round(v*scale) for v in value) if isinstance(value,tuple) else round(value*scale)
                               for key,value in values.items()})


def install_dpi(root):
    if not hasattr(root,'_ui_dpi_tracker'):root._ui_dpi_tracker=DpiTracker(root)
    return root._ui_dpi_tracker


def watch_scale(widget,callback):
    tracker=install_dpi(widget._root());window=widget.winfo_toplevel()
    tracker.watch_window(window)
    tracker.windows[window]['widgets'][widget]=weakref.WeakMethod(callback)


def scale_styles(root,style,names):
    tracker=install_dpi(root)
    for name in names:
        if name not in tracker.styles:
            values={}
            options=style.configure(name) or {}
            for key in ('padding','rowheight'):
                if key not in options:continue
                try:
                    values[key]=tuple(float(v) for v in root.tk.splitlist(options[key])) if key=='padding' else float(options[key])
                except (TypeError,ValueError,tk.TclError):continue
            if values:tracker.styles[name]=(style,name,values)
        if name in tracker.styles:tracker._style(*tracker.styles[name],ui_scale(root))
