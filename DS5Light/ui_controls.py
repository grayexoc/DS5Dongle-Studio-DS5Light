"""Small static controls with predictable colors across Windows themes."""
import base64
import struct
import zlib
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from ui_dpi import px,ui_scale,watch_scale


def widget_trace(widget, variable, callback):
    """Keep a variable callback only as long as its owning widget exists."""
    token=variable.trace_add('write',callback)
    def cleanup(event):
        if event.widget is widget:
            try:variable.trace_remove('write',token)
            except tk.TclError:pass
    widget.bind('<Destroy>',cleanup,add='+')
    return token


def draw_ui_symbol(canvas, kind, x, y, size, color, tags=()):
    """Draw small theme icons independently of installed symbol fonts."""
    import math
    def line(*points):
        canvas.create_line(*points, fill=color, width=1.5, capstyle='round', joinstyle='round', tags=tags)
    if kind == 'waveform':
        points=[]
        for px,py in ((.05,.5),(.2,.5),(.32,.2),(.45,.85),(.59,.15),(.73,.68),(.84,.5),(.95,.5)):
            points.extend((x+size*px,y+size*py))
        line(*points)
    elif kind == 'camera':
        a, b, c, d = x+1, y+3, x+size-1, y+size-2
        arm=size*.27
        for px, py, dx, dy in ((a,b,1,1),(c,b,-1,1),(a,d,1,-1),(c,d,-1,-1)):
            line(px+dx*arm,py,px,py,px,py+dy*arm)
        canvas.create_oval(x+size*.32,y+size*.32,x+size*.68,y+size*.68,
                           outline=color,width=1.5,tags=tags)
    elif kind == 'channels':
        for cx in (x+size*.25,x+size*.75):
            canvas.create_rectangle(cx-3,y+2,cx+3,y+size-2,
                                    outline=color,width=1.5,tags=tags)
            canvas.create_oval(cx-1.5,y+size*.52,cx+1.5,y+size*.52+3,
                               outline=color,width=1,tags=tags)
            canvas.create_oval(cx-.8,y+4,cx+.8,y+5.6,
                               fill=color,outline='',tags=tags)
    elif kind == 'filter':
        line(x+1,y+3,x+size-1,y+3,x+size*.62,y+size*.57,
             x+size*.62,y+size-2,x+size*.38,y+size-2,
             x+size*.38,y+size*.57,x+1,y+3)
    elif kind == 'sliders':
        for fraction, position in ((.2,.65),(.5,.32),(.8,.58)):
            cy=y+size*fraction
            cx=x+size*position
            line(x+1,cy,cx-2,cy)
            line(cx+2,cy,x+size-1,cy)
            canvas.create_rectangle(cx-2,cy-2,cx+2,cy+2,
                                    outline=color,width=1.5,tags=tags)
    elif kind == 'gear':
        cx,cy=x+size/2,y+size/2
        points=[]
        for i in range(32):
            angle=math.tau*i/32
            radius=size*(.47 if i%4 in (0,1) else .35)
            points.extend((cx+math.cos(angle)*radius,cy+math.sin(angle)*radius))
        canvas.create_polygon(*points,fill='',outline=color,width=1.5,joinstyle='round',tags=tags)
        canvas.create_oval(cx-size*.16,cy-size*.16,cx+size*.16,cy+size*.16,
                           outline=color,width=1.5,tags=tags)


class RoundedCard(tk.Frame):
    """Border host and padded content are separate sibling layers.

    Populate ``content`` and manage this outer frame with grid/pack. The drawing
    canvas never inherits content padding and cannot be covered by its children.
    """
    def __init__(self, parent, *, background, surface, outline, inset_x=14,
                 inset_y=14, radius=10):
        super().__init__(parent, bg=background, borderwidth=0,
                         highlightthickness=0)
        self._surface, self._outline, self._radius = surface, outline, radius
        self._insets=(inset_x,inset_y)
        self._backdrop = tk.Canvas(self, bg=background, borderwidth=0,
                                   highlightthickness=0, takefocus=0)
        self._backdrop.place(x=0, y=0, relwidth=1, relheight=1, bordermode='ignore')
        self.content = tk.Frame(self, bg=surface, borderwidth=0, highlightthickness=0)
        self.content.pack(fill='both', expand=True, padx=px(self,inset_x), pady=px(self,inset_y))
        self._backdrop.bind('<Configure>', self._draw_card)
        watch_scale(self,self._scale_card)

    def _scale_card(self):
        self.content.pack_configure(padx=px(self,self._insets[0]),pady=px(self,self._insets[1]))
        self._draw_card()

    def _draw_card(self, event=None):
        canvas = self._backdrop
        canvas.delete('all')
        left, top, right, bottom = .5, .5, canvas.winfo_width()-1.5, canvas.winfo_height()-1.5
        r = min(px(self,self._radius), max(0, (right-left)/2), max(0, (bottom-top)/2))
        if r <= 0:
            return
        canvas.create_rectangle(left+r, top, right-r, bottom,
                                fill=self._surface, outline='')
        canvas.create_rectangle(left, top+r, right, bottom-r,
                                fill=self._surface, outline='')
        for x, y, start in ((left, top, 90), (right-2*r, top, 0),
                            (left, bottom-2*r, 180), (right-2*r, bottom-2*r, 270)):
            canvas.create_arc(x, y, x+2*r, y+2*r, start=start, extent=90,
                              style='pieslice', fill=self._surface, outline='')
            canvas.create_arc(x, y, x+2*r, y+2*r, start=start, extent=90,
                              style='arc', outline=self._outline)
        for points in ((left+r,top,right-r,top), (left+r,bottom,right-r,bottom),
                       (left,top+r,left,bottom-r), (right,top+r,right,bottom-r)):
            canvas.create_line(*points, fill=self._outline)


class AutoScrollbar(ttk.Scrollbar):
    """A grid-managed scrollbar shown only while its content overflows."""
    def set(self, first, last):
        overflow = float(first) > .00001 or float(last) < .99999
        if overflow:
            if not self.grid_info():
                self.grid()
        elif self.grid_info():
            self.grid_remove()
        super().set(first, last)


class DiagnosticCanvas(tk.Canvas):
    """Readonly diagnostic text above a bottom-right transparent watermark."""
    def __init__(self, parent, *, font, foreground, background, images):
        super().__init__(parent, bg=background, height=60, width=1,
                         borderwidth=0, highlightthickness=0, takefocus=1,
                         yscrollincrement=20)
        self._font, self._foreground = font, foreground
        self._text = ''
        self._images = images
        self._scrollcommand = None
        self._image_item = self.create_image(0, 0, anchor='se')
        self.configure(yscrollcommand=self._scrolled)
        self.bind('<MouseWheel>', self._wheel)
        self.bind('<Control-c>', self._copy)
        self.bind('<Button-1>', lambda _event: self.focus_set())

    def set_scrollcommand(self, callback):
        self._scrollcommand = callback

    def _scrolled(self, first, last):
        self._position_image()
        if self._scrollcommand:
            self._scrollcommand(first, last)

    def _position_image(self):
        self.coords(self._image_item, max(0,self.winfo_width()-1),
                    self.canvasy(max(0,self.winfo_height()-1)))

    def _wheel(self, event):
        self.yview_scroll(-int(event.delta/120), 'units')
        return 'break'

    def _copy(self, _event):
        self.clipboard_clear()
        self.clipboard_append(self._text)
        return 'break'

    def set_text(self, text):
        self._text = text
        self.fit_text()

    def fit_text(self):
        if not self.winfo_viewable():
            return
        width, height = self.winfo_width(), self.winfo_height()
        if width < 4 or height < 4:
            return
        position = self.yview()[0]
        lines = []
        for line in self._text.split('\n'):
            while line and self._font.measure(line) > width-8:
                low, high = 1, len(line)
                while low < high:
                    middle = (low+high+1)//2
                    if self._font.measure(line[:middle]) <= width-8:
                        low = middle
                    else:
                        high = middle-1
                split = max(1, low)
                lines.append(line[:split])
                line = line[split:]
            lines.append(line)
        line_height = self._font.metrics('linespace')
        gap = max(0, (height-4-len(lines)*line_height)/len(lines)) if len(lines)>1 else 0
        self.delete('diagnostic-line')
        for index, line in enumerate(lines):
            self.create_text(2, 2+gap/2+index*(line_height+gap), anchor='nw',
                             text=line, font=self._font, fill=self._foreground,
                             tags='diagnostic-line')
        # Select the former tier at 150% size; fit inside the actual viewport.
        fitting = [image for image in self._images
                   if image.width()/1.5 <= width*.55 and image.height()/1.5 <= height*.85
                   and image.width() <= width-16 and image.height() <= height-16]
        image = fitting[-1] if fitting else None
        self.itemconfigure(self._image_item, image=image or '')
        self.tag_lower(self._image_item)
        self.configure(scrollregion=(0,0,width,max(height,len(lines)*(line_height+gap)+4)))
        self.yview_moveto(position)
        self._position_image()


def install_combobox_selection_cleanup(root, foreground, background, disabled_foreground, disabled_background):
    """Keep readonly values unshaded without changing popup row selection."""
    from tkinter import ttk
    style = ttk.Style(root)
    style.map('TCombobox',
              selectbackground=[('disabled', disabled_background), ('!disabled', background)],
              selectforeground=[('disabled', disabled_foreground), ('!disabled', foreground)])
    root.option_add('*TCombobox.exportSelection', False)

    def guard_wheel(event):
        widget=event.widget
        if not getattr(widget,'_wheel_selected',False):return 'break'

    root.bind_class('DS5ComboWheel','<MouseWheel>',guard_wheel)
    root.bind_class('DS5ComboWheel','<Button-1>',lambda e:setattr(e.widget,'_wheel_selected',True))
    root.bind_class('DS5ComboWheel','<FocusOut>',lambda e:setattr(e.widget,'_wheel_selected',False))

    def schedule(event):
        widget = event.widget
        if not isinstance(widget, ttk.Combobox):
            return

        tags=widget.bindtags()
        if 'DS5ComboWheel' not in tags:widget.bindtags((tags[0],'DS5ComboWheel')+tags[1:])

        def clear():
            try:
                if widget.winfo_exists() and ('readonly' in widget.state() or 'disabled' in widget.state()):
                    widget.configure(exportselection=False)
                    widget.selection_clear()
                    widget.icursor(0)
                    widget.xview_moveto(0)
            except tk.TclError:
                pass
        # Tk's own selection handler runs first; clear its entry selection only
        # after all existing application callbacks have completed.
        widget.after_idle(clear)

    for sequence in ('<<ComboboxSelected>>', '<FocusIn>', '<FocusOut>', '<ButtonRelease-1>', '<KeyRelease>', '<Map>'):
        root.bind_class('TCombobox', sequence, schedule, add='+')


def circle_image(master, color, size=14, radio=False, selected=False):
    """Generate an antialiased transparent circle once, with no image library."""
    root=master._root()
    if not hasattr(root,'_circle_image_cache'):root._circle_image_cache={}
    key=(color,size,radio,selected)
    if key in root._circle_image_cache:return root._circle_image_cache[key]
    rgb=bytes.fromhex(color.lstrip('#'))
    radius=size/2-1
    rows=bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            coverage=0
            for sy in range(4):
                for sx in range(4):
                    d=((x+(sx+.5)/4-size/2)**2+(y+(sy+.5)/4-size/2)**2)**.5
                    visible=d<=radius
                    if radio:
                        visible=radius-max(1.6,1.6*size/20)<=d<=radius or selected and d<=radius*.45
                    coverage+=bool(visible)
            rows.extend(rgb); rows.append(round(255*coverage/16))
    def chunk(name,data):
        return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,6,0,0,0))
    png+=chunk(b'IDAT',zlib.compress(bytes(rows)))+chunk(b'IEND',b'')
    result=tk.PhotoImage(master=root,data=base64.b64encode(png).decode('ascii'))
    root._circle_image_cache[key]=result
    return result


class RadioChoice(tk.Canvas):
    def __init__(self,parent,text,value,variable,command,background,foreground,muted,accent,disabled):
        self.font=tkfont.Font(family='맑은 고딕',size=10)
        super().__init__(parent,width=self.font.measure(text)+px(parent,30),height=max(px(parent,28),self.font.metrics('linespace')+px(parent,8)),bg=background,
                         highlightthickness=0,highlightbackground=background,highlightcolor=background,
                         takefocus=1,borderwidth=0,cursor='hand2')
        self.text=text; self.value=value; self.variable=variable; self.command=command
        self.foreground=foreground; self.disabled=disabled; self.enabled=True
        self._accent,self._muted=accent,muted;self._icon_scale=None
        widget_trace(self,self.variable,lambda *_:self.draw())
        self.bind('<Button-1>',lambda _:self.invoke())
        self.bind('<space>',lambda _:self.invoke()); self.bind('<Return>',lambda _:self.invoke())
        watch_scale(self,self.draw)
        self.draw()
    def invoke(self):
        if self.enabled:
            self.focus_set(); self.variable.set(self.value); self.command()
        return 'break'
    def set_enabled(self,enabled):
        if enabled==self.enabled: return
        self.enabled=enabled; self.configure(takefocus=int(enabled),cursor='hand2' if enabled else 'arrow'); self.draw()
    def draw(self):
        scale=ui_scale(self)
        if self._icon_scale!=scale:
            check=getattr(self,'_check_style',False)
            self.icons={(enabled,selected):circle_image(self,
                self._accent if enabled and selected else self.disabled if not enabled or check and selected else self._muted,
                size=max(1,px(self,20)),radio=not selected if check else True,selected=selected)
                for enabled in (True,False) for selected in (True,False)}
            self._icon_scale=scale
        height=max(px(self,28),self.font.metrics('linespace')+px(self,8))
        self.configure(width=self.font.measure(self.text)+px(self,30),height=height)
        self.delete('all')
        self.create_image(px(self,11),height/2,image=self.icons[(self.enabled,self.variable.get()==self.value)])
        self.create_text(px(self,26),height/2,text=self.text,anchor='w',font=self.font,
                         fill=self.foreground if self.enabled else self.disabled)


class CircleCheck(RadioChoice):
    """Independent boolean setting, with a gold disk for its checked state."""
    def __init__(self,parent,text,variable,command,**colors):
        self._check_style=True
        super().__init__(parent,text,True,variable,command,**colors)
    def invoke(self):
        if self.enabled:
            self.focus_set(); self.variable.set(not self.variable.get()); self.command()
        return 'break'


class SectionTitle(tk.Canvas):
    """Bold section title with a gold symbol and compact tracking."""
    def __init__(self,parent,number,title,background,foreground,accent):
        self.font=tkfont.Font(family='맑은 고딕',size=12,weight='bold')
        self.number,self.title,self._title_foreground,self._title_accent=number,title,foreground,accent
        super().__init__(parent,bg=background,highlightthickness=0,borderwidth=0,takefocus=0)
        watch_scale(self,self._draw_title);self._draw_title()

    def _draw_title(self):
        self.delete('all');self.tracking=-px(self,1)
        def advance(character):
            width=self.font.measure(character)+self.tracking
            return width*.5 if character.isspace() else width
        vector=self.number in ('camera','filter','channels')
        icon=px(self,18);gap=px(self,4)
        number_width=icon if vector else sum(advance(c) for c in self.number)
        height=self.font.metrics('linespace')+px(self,4)
        self.configure(width=number_width+gap+sum(advance(c) for c in self.title)+px(self,4),height=height)
        if vector:draw_ui_symbol(self,self.number,0,(height-icon)/2,icon,self._title_accent)
        for text,x,color in [(('' if vector else self.number),0,self._title_accent),(self.title,number_width+gap,self._title_foreground)]:
            for character in text:
                self.create_text(x,px(self,1),text=character,anchor='nw',font=self.font,fill=color)
                x+=advance(character)

_SWITCH_CARD='#151515'
_SWITCH_ACCENT='#d6ad52'

class Switch(tk.Canvas):

    """Static native Tk switch: no animation, web engine or polling."""

    def __init__(self,parent,variable,command):

        super().__init__(parent,width=px(parent,44),height=px(parent,26),bg=_SWITCH_CARD,highlightthickness=1,

                         highlightbackground=_SWITCH_CARD,highlightcolor=_SWITCH_ACCENT,takefocus=1,cursor='hand2')

        self.variable=variable; self.command=command; self.enabled=True

        self.bind('<Button-1>',lambda e:self.invoke())

        self.bind('<space>',lambda e:self.invoke())

        self.bind('<Return>',lambda e:self.invoke())

        widget_trace(self,variable,lambda *args:self.draw())

        watch_scale(self,self._scale_switch)
        self.draw()

    def _scale_switch(self):
        self.configure(width=px(self,44),height=px(self,26));self.draw()

    def invoke(self):

        if self.enabled:

            self.variable.set(not self.variable.get()); self.command()

        return 'break'

    def set_enabled(self,enabled):

        if self.enabled==enabled: return

        self.enabled=enabled; self.configure(takefocus=int(enabled),cursor='hand2' if enabled else 'arrow'); self.draw()

    def draw(self):

        self.delete('all')

        on=self.variable.get(); color=_SWITCH_ACCENT if on and self.enabled else '#3a3832'

        self.create_oval(*(px(self,v) for v in (2,3,22,23)),fill=color,outline=color)

        self.create_oval(*(px(self,v) for v in (22,3,42,23)),fill=color,outline=color)

        self.create_rectangle(*(px(self,v) for v in (12,3,32,23)),fill=color,outline=color)

        x=25 if on else 5

        knob='#2b2110' if on and self.enabled else '#c4c0b6' if self.enabled else '#77736b'

        self.create_oval(*(px(self,v) for v in (x,6,x+14,20)),fill=knob,outline=knob)
