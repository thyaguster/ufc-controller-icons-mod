"""Original monochrome keycaps and conservative PS5 BC3 encoding."""
from __future__ import annotations
import functools
import math
from pathlib import Path
import re
import struct

from patcher_core import PatchError, check

ROOT=Path(__file__).resolve().parent
FONT=ROOT/'keyboard-art/font/BarlowCondensed-Bold.ttf'
if not FONT.is_file():
    FONT=ROOT/'ufc4_keyboard/keyboard-art/font/BarlowCondensed-Bold.ttf'


def descriptor(name):
    """Return controls represented by an existing texture or Flash symbol."""
    name=name.rsplit('/',1)[-1].split('.')[-1].lower()
    name=re.sub(r'^btn_|_mc$','',name)
    name=name.replace('_highlight','').replace('_ps','').replace('_xb','')
    name=re.sub(r'^ue_','',name)
    # EA's names follow Cross/A, Circle/B, Triangle/Y, Square/X order.
    # Verified against the original PS and Xbox texture artwork, not enum order.
    direct={'digital_one':['Cross'],'digital_two':['Circle'],'digital_three':['Triangle'],
            'digital_four':['Square'],'left_bumper':['L1'],'right_bumper':['R1'],
            'left_trigger':['L2'],'right_trigger':['R2'],'left_on_trigger':['L2'],
            'right_on_trigger':['R2'],'left_right_bumper':['L1','R1'],
            'left_right_trigger':['L2','R2'],'select':['TouchPad'],'start':['Options'],
            'guide':['Guide']}
    cleaned=re.sub(r'_(?:hold_skip_widget|hold|precanned_message)$','',name)
    if cleaned in direct:return dict(controls=direct[cleaned],layout='row')
    m=re.fullmatch(r'(las|ras|dpad)(?:_(.*))?',name)
    if not m:return None
    family,suffix=m.groups();suffix=suffix or 'a'
    if suffix=='c':return dict(controls=['L3' if family=='las' else 'R3'],layout='row')
    prefix={'las':'LeftStick','ras':'RightStick','dpad':''}[family]
    if suffix.startswith('gesture_'):
        suffix=suffix[len('gesture_'):]
        if suffix in ('advanced_position','submission_attempts'):suffix='a'
    suffix=suffix.replace('_','')
    if suffix in ('a','large'):suffix='uldr'
    dirs={'u':'Up','d':'Down','l':'Left','r':'Right'}
    if not suffix or any(c not in dirs for c in suffix):return None
    controls=[prefix+dirs[c] for c in suffix]
    return dict(controls=controls,layout='cross' if len(controls)>=3 else 'row')


def label(value):
    if not value:return '-'
    special={'Return':'ENT','Return2':'ENT','Escape':'ESC','Space':'SPC',
             'Backspace':'BS','CapsLock':'CAPS','PageUp':'PGUP','PageDown':'PGDN',
             'Left Shift':'SHF','Right Shift':'SHF','Left Ctrl':'CTRL',
             'Right Ctrl':'CTRL','Left Alt':'ALT','Right Alt':'ALT',
             'Left GUI':'WIN','Right GUI':'WIN','PrintScreen':'PRTSC',
             'ScrollLock':'SCRLK','Numlock':'NUM','Application':'MENU',
             'VolumeDown':'VOL-','VolumeUp':'VOL+','Mouse:X1':'M4','Mouse:X2':'M5'}
    if value in special:return special[value]
    if value.startswith('Keypad '):return 'NUM '+value[7:].upper()
    return value.upper()


def pillow():
    try:
        from PIL import Image,ImageDraw,ImageFont
    except ImportError as exc:
        raise PatchError('Keyboard artwork needs Pillow. From the source folder run: python -m pip install -r requirements.txt') from exc
    return Image,ImageDraw,ImageFont


@functools.lru_cache(maxsize=1)
def _kenney_pack():
    import sys, zipfile
    cands = [ROOT / 'keyboard-art' / 'kenney_kb_prompts.zip']
    mp = getattr(sys, '_MEIPASS', None)
    if mp:
        cands.insert(0, Path(mp) / 'ufc4_keyboard' / 'keyboard-art' / 'kenney_kb_prompts.zip')
    for p in cands:
        if p.is_file():
            with zipfile.ZipFile(p) as z:
                return {n: z.read(n) for n in z.namelist() if n.endswith('.png')}
    return {}


def _kenney_filename(value):
    if not value:
        return None
    direct = {
        'Space': 'keyboard_space_icon.png',
        'Left Shift': 'keyboard_shift_icon.png', 'Right Shift': 'keyboard_shift_icon.png',
        'Return': 'keyboard_return.png', 'Return2': 'keyboard_return.png',
        'Tab': 'keyboard_tab_icon.png',
        'Backspace': 'keyboard_backspace_icon.png',
        'Escape': 'keyboard_escape.png',
        'Left Ctrl': 'keyboard_ctrl.png', 'Right Ctrl': 'keyboard_ctrl.png',
        'Left Alt': 'keyboard_alt.png', 'Right Alt': 'keyboard_alt.png',
        'CapsLock': 'keyboard_capslock_icon.png',
        'Up': 'keyboard_arrow_up.png', 'Down': 'keyboard_arrow_down.png',
        'Left': 'keyboard_arrow_left.png', 'Right': 'keyboard_arrow_right.png',
        'Mouse:Left': 'mouse_left.png', 'Mouse:Right': 'mouse_right.png',
        'Mouse:Middle': 'mouse_scroll.png',
        'Mouse:X1': 'mouse_side_back.png', 'Mouse:X2': 'mouse_side_forward.png',
    }
    if value in direct:
        return direct[value]
    low = value.lower()
    if len(low) == 1 and low.isalnum():
        return f'keyboard_{low}.png'
    if re.fullmatch(r'f([1-9]|1[0-2])', low):
        return f'keyboard_{low}.png'
    return None


@functools.lru_cache(maxsize=256)
def _kenney_image(filename, state='normal'):
    import io
    pack = _kenney_pack()
    raw = pack.get(filename)
    if not raw:
        return None
    Image, _, _ = pillow()
    im = Image.open(io.BytesIO(raw)).convert('RGBA')
    bb = im.getchannel('A').point(lambda v: 255 if v > 15 else 0).getbbox()
    if bb:
        im = im.crop(bb)
    if state != 'normal':
        r, g, b, a = im.split()
        inv = lambda ch: ch.point(lambda v: 255 - v)
        im = Image.merge('RGBA', (inv(r), inv(g), inv(b), a))
    return im


def _cap(size,value,state,unit=None):
    Image,ImageDraw,ImageFont=pillow()
    w,h=size;im=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(im)
    kf=_kenney_filename(value)
    spr=_kenney_image(kf,state) if kf else None
    if spr is not None:
        from PIL import ImageFilter
        max_h=min(h,unit) if unit is not None else min(h,max(w,round(w*1.05)))
        sc=min(w/spr.width,max_h/spr.height)
        tw=max(1,round(spr.width*sc));th=max(1,round(spr.height*sc))
        fitted=spr.resize((tw,th),Image.Resampling.LANCZOS)
        if tw < spr.width:
            fitted=fitted.filter(ImageFilter.UnsharpMask(radius=0.8,percent=130,threshold=2))
        im.alpha_composite(fitted,((w-tw)//2,(h-th)//2))
        return im
    if unit is not None:
        ch=min(h,unit)
        lbl=label(value) if value not in ('Up','Down','Left','Right','Mouse:Left','Mouse:Right','Mouse:Middle') else ''
        cw=min(w,round(ch*(0.92+0.20*min(len(lbl),4)))) if len(lbl)>1 else min(w,ch)
    else:
        cw=w;ch=min(h,max(w,round(w*1.05)))
    cx=(w-cw)//2;cy=(h-ch)//2
    ink=(36,36,36,255) if state=='normal' else (250,250,250,255)
    face=(250,250,250,255) if state=='normal' else (36,36,36,255)
    edge=max(1,ch//24);pad=max(1,ch//20)
    draw.rounded_rectangle((cx+pad,cy+pad,cx+cw-pad-1,cy+ch-pad-1),radius=max(2,ch//8),fill=face,
                           outline=ink if state!='normal' else None,width=edge)
    if value in ('Up','Down','Left','Right'):
        pts=[(.5,.23),(.77,.5),(.60,.5),(.60,.77),(.40,.77),(.40,.5),(.23,.5)]
        theta={'Up':0,'Right':90,'Down':180,'Left':270}[value]*math.pi/180
        points=[(cx+((x-.5)*math.cos(theta)-(y-.5)*math.sin(theta)+.5)*cw,
                 cy+((x-.5)*math.sin(theta)+(y-.5)*math.cos(theta)+.5)*ch) for x,y in pts]
        draw.polygon(points,fill=ink)
    elif value in ('Mouse:Left','Mouse:Right','Mouse:Middle'):
        x0,y0,x1,y1=cx+.30*cw,cy+.15*ch,cx+.70*cw,cy+.85*ch
        draw.rounded_rectangle((x0,y0,x1,y1),radius=max(2,.16*ch),outline=ink,width=max(1,ch//20))
        draw.line((x0,cy+.46*ch,x1,cy+.46*ch),fill=ink,width=max(1,ch//28))
        draw.line((cx+.5*cw,y0,cx+.5*cw,cy+.46*ch),fill=ink,width=max(1,ch//28))
        if value=='Mouse:Middle':draw.rounded_rectangle((cx+.45*cw,cy+.23*ch,cx+.55*cw,cy+.42*ch),radius=max(1,ch//36),fill=ink)
        else:
            left,right=(.35,.45) if value=='Mouse:Left' else (.55,.65)
            draw.rounded_rectangle((cx+left*cw,cy+.24*ch,cx+right*cw,cy+.39*ch),radius=max(1,ch//40),fill=ink)
    else:
        text=label(value)
        font=ImageFont.truetype(str(FONT),max(6,round(ch*.87)))
        box=draw.textbbox((0,0),text,font=font)
        glyph=Image.new('RGBA',(box[2]-box[0]+4,box[3]-box[1]+4))
        ImageDraw.Draw(glyph).text((2-box[0],2-box[1]),text,font=font,fill=ink)
        scale=min((cw*.78)/glyph.width,(ch*.58)/glyph.height)
        target_w=max(1,round(glyph.width*scale));target_h=max(1,round(glyph.height*scale))
        glyph=glyph.resize((target_w,target_h),Image.Resampling.LANCZOS)
        im.alpha_composite(glyph,(cx+(cw-glyph.width)//2,cy+(ch-glyph.height)//2))
    return im


@functools.lru_cache(maxsize=768)
def _render(width,height,controls,layout,values,state):
    Image,_,_=pillow();factor=4
    w,h=width*factor,height*factor
    image=Image.new('RGBA',(w,h))
    if len(controls)==1:
        unit=round(min(width,height)*.56*factor) if min(width,height)>=96 else round(26*factor)
        image.alpha_composite(_cap((w,h),values[0],state,unit=unit))
    elif set(values)<={'Up','Down','Left','Right'} and _kenney_pack():
        vset=set(values)
        cname=('keyboard_arrows_all.png' if len(vset)>=3 else
               'keyboard_arrows_horizontal.png' if vset=={'Left','Right'} else
               'keyboard_arrows_vertical.png' if vset=={'Up','Down'} else 'keyboard_arrows_all.png')
        spr=_kenney_image(cname,state)
        if spr is not None:
            max_h=round(min(w,h)*.85) if min(width,height)>=96 else min(h,round(30*factor))
            sc=min(w/spr.width,max_h/spr.height)
            tw,th=max(1,round(spr.width*sc)),max(1,round(spr.height*sc))
            image.alpha_composite(spr.resize((tw,th),Image.Resampling.LANCZOS),((w-tw)//2,(h-th)//2))
    elif layout=='cross':
        gap=max(2,factor)
        cell=max(1,min((w-2*gap)//3,(h-gap)//2))
        total_w=3*cell+2*gap;total_h=2*cell+gap
        ox=(w-total_w)//2;oy=(h-total_h)//2
        pos_map={'Up':(ox+cell+gap,oy),'Left':(ox,oy+cell+gap),
                 'Down':(ox+cell+gap,oy+cell+gap),'Right':(ox+2*(cell+gap),oy+cell+gap)}
        for control,value in zip(controls,values):
            direction=next((d for d in ('Up','Down','Left','Right') if control.endswith(d)),None)
            image.alpha_composite(_cap((cell,cell),value,state),pos_map[direction])
    else:
        gap=max(2,w//30);cw=max(1,(w-gap*(len(controls)-1))//len(controls));ch=min(h,cw)
        for i,value in enumerate(values):image.alpha_composite(_cap((cw,ch),value,state),(i*(cw+gap),(h-ch)//2))
    return image.resize((width,height),Image.Resampling.LANCZOS).tobytes()


def render(width,height,desc,bindings,state='normal'):
    check(0<width<=1024 and 0<height<=1024,'Unsupported icon dimensions.')
    controls=tuple(desc['controls']);values=tuple(bindings.controls.get(c) for c in controls)
    return _render(width,height,controls,desc['layout'],values,state)


def bc3_block(pixels):
    alphas=[p[3] for p in pixels];a0=max(alphas);a1=min(alphas)
    if a0==a1:a1=0 if a0 else 255
    ap=[a0,a1]
    if a0>a1:ap += [((7-i)*a0+i*a1)//7 for i in range(1,7)]
    else:ap += [((5-i)*a0+i*a1)//5 for i in range(1,5)]+[0,255]
    ai=sum(min(range(8),key=lambda k:abs(ap[k]-a))<<(3*i) for i,a in enumerate(alphas))
    # The artwork is monochrome; fixed white/black RGB565 endpoints give four
    # stable gray levels and independent alpha, without a native compressor.
    colors=[255,0,170,85]
    ci=sum(min(range(4),key=lambda k:abs(colors[k]-p[0]))<<(2*i) for i,p in enumerate(pixels))
    return bytes((a0,a1))+ai.to_bytes(6,'little')+struct.pack('<HHI',65535,0,ci)


@functools.lru_cache(maxsize=256)
def _swizzle(width,height,length):
    bw,bh=width//4,height//4
    check(width%4==0 and height%4==0,'Unsupported BC3 dimensions.')
    # PS5 BC3 UI allocations use 16x16-block tiles (64x64 pixels).
    # The two upper intra-tile coordinate bits are Y3 then X3. This was
    # independently checked by reconstructing an existing 84x56 texture.
    pitch=((bw+15)//16)*16
    result=[]
    for y in range(bh):
        for x in range(bw):
            low=sum(v<<p for v,p in zip((x&1,(x>>1)&1,(x>>2)&1,(x>>3)&1,
                                         y&1,(y>>1)&1,(y>>2)&1,(y>>3)&1),(2,3,5,7,0,1,4,6)))
            offset=(((y//16)*(pitch//16)+x//16)*256+low)*16
            check(offset+16<=length,'Icon allocation is too small for its PS5 tile layout.')
            result.append((x,y,offset))
    return result


def texture(original,info,bindings):
    from patcher_core import unframe
    raw,frames=unframe(original)
    w,h=info['width'],info['height']
    rgba=render(w,h,info['descriptor'],bindings,info.get('state','normal'))
    pixels=[tuple(rgba[i:i+4]) for i in range(0,len(rgba),4)]
    # Alpha zero blocks are explicitly transparent in the padded allocation.
    transparent=bc3_block([(0,0,0,0)]*16)
    output=bytearray(transparent*(len(raw)//16))
    for x,y,offset in _swizzle(w,h,len(raw)):
        block=[pixels[(y*4+dy)*w+x*4+dx] for dy in range(4) for dx in range(4)]
        output[offset:offset+16]=bc3_block(block)
    result=bytearray(original)
    for stored,plain,length in frames:result[stored:stored+length]=output[plain:plain+length]
    return bytes(result)
