"""User supplied controller artwork with native USB input highlighting."""
from pathlib import Path
import tkinter as tk
import xml.etree.ElementTree as ET


def active_parts(state):
    if not state:return frozenset()
    mask=state['mask']
    ids={0:'path68',1:'path67',2:'path71',3:'path69',4:'g84',5:'g79',
         6:'g80',7:'g83',8:'path220',9:'path226',10:'L2',11:'R2',
         12:'g98',13:'g103',14:'g76',15:'g254',16:'path229',17:'path270',18:'rect228'}
    parts={name for bit,name in ids.items() if mask&(1<<bit)}
    if state.get('l2',0)>20:parts.add('L2')
    if state.get('r2',0)>20:parts.add('R2')
    for x,y,name in [('lx','ly','g76'),('rx','ry','g254')]:
        if max(abs(state.get(x,128)-128),abs(state.get(y,128)-128))>24:parts.add(name)
    if (state.get('touch') or {}).get('down'):parts.add('path270')
    return frozenset(parts)


class ControllerArt:
    def __init__(self,master):
        self.master=master
        source=Path(__file__).resolve().parent
        self.svg=(source/'assets'/'diagnostic-controller.svg').read_text(encoding='utf-8')
        master.tk.call('lappend','auto_path',str(source/'vendor'/'tksvg0.16'))
        master.tk.call('package','require','tksvg','0.16')
        self.key=None

    def image(self,width,height,state):
        parts=active_parts(state)
        key=(max(1,int(width)),max(1,int(height)),parts)
        if key==self.key:return self.photo
        ET.register_namespace('','http://www.w3.org/2000/svg')
        root=ET.fromstring(self.svg.replace('#000000','#d6ad52').replace('fill:#ffffff','fill:none').replace('fill:#FFFFFF','fill:none'))
        for node in root.iter():
            if node.get('id')=='path228':node.set('style',node.get('style','')+';fill:none')
            if node.get('id') in ('ellipse73','ellipse74','ellipse250','ellipse251'):
                node.set('style',node.get('style','')+';fill:#151515;stroke:#d6ad52;stroke-width:6')
            if node.get('id')=='path229':node.set('style',node.get('style','')+';fill:#d6ad52')
            if node.get('id')=='rect228':node.set('style',node.get('style','')+';fill:#151515;stroke:#d6ad52')
        def visit(node,active=False):
            active=active or node.get('id') in parts
            if active and node.tag.split('}')[-1] in ('path','rect','circle','ellipse','polygon'):
                style=node.get('style','')
                node.set('style',style+';fill:#fff2b9;stroke:#fff2b9')
            for child in node:visit(child,active)
        visit(root)
        self.photo=tk.PhotoImage(master=self.master,data=ET.tostring(root,encoding='unicode'),
                                format=('svg','-scaletoheight',min(key[1],round(key[0]*210/297))))
        self.key=key
        return self.photo
