# Renders: intro, question cards, outro (full frames) and verdict stamp overlays (RGBA) as raw frames on stdout
import sys, math, textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
S=sys.argv[1]; sys.path.insert(0,S+"/scripts"); from content import Q
F=S+"/fonts/"; W,H=1080,1920; FPS=30
def KA(w,s): return ImageFont.truetype(F+f"NotoSansGeorgian-{w}.ttf",s)
def EN(w,s): return ImageFont.truetype(F+f"Montserrat-{w}.ttf",s)
def ease(x): x=max(0,min(1,x)); return 1-(1-x)**3
def back(x): x=max(0,min(1,x)); c=1.7; return 1+(c+1)*(x-1)**3+c*(x-1)**2
TMP=ImageDraw.Draw(Image.new("RGBA",(1,1)))
def tl(t,font,spacing=0): return sum(TMP.textlength(c,font=font) for c in t)+spacing*(len(t)-1) if spacing else TMP.textlength(t,font=font)
def layer(lines,font,fill,spacing=0,shadow=0,lh=1.18,align="c"):
    if isinstance(lines,str): lines=[lines]
    asc,desc=font.getmetrics(); h=int((asc+desc)*lh); pad=40
    w=int(max(tl(l,font,spacing) for l in lines)); L=Image.new("RGBA",(w+2*pad,h*len(lines)+2*pad),(0,0,0,0))
    def draw(d,col):
        for i,l in enumerate(lines):
            lw=tl(l,font,spacing); x=pad+((w-lw)/2 if align=="c" else 0); y=pad+i*h
            if spacing:
                for c in l: d.text((x,y),c,font=font,fill=col); x+=TMP.textlength(c,font=font)+spacing
            else: d.text((x,y),l,font=font,fill=col)
    if shadow:
        sh=Image.new("RGBA",L.size,(0,0,0,0)); draw(ImageDraw.Draw(sh),(0,0,0,shadow)); L.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    draw(ImageDraw.Draw(L),fill); return L
def wrap(t,font,maxw):
    words=t.split(); lines=[""]
    for w in words:
        c=(lines[-1]+" "+w).strip()
        if tl(c,font)<=maxw: lines[-1]=c
        else: lines.append(w)
    return lines
def put(c,L,cx,cy,t,t0,dur=0.5,dy=50,scale=False,alpha=1.0):
    p=(t-t0)/dur
    if p<=0: return
    e=ease(p); a=e*alpha
    if scale:
        s=0.55+0.45*back(p); L=L.resize((max(1,int(L.width*s)),max(1,int(L.height*s))),Image.LANCZOS)
    if a<1: L=L.copy(); L.putalpha(L.getchannel("A").point(lambda v:int(v*a)))
    c.alpha_composite(L,(int(cx-L.width/2),int(cy-L.height/2+dy*(1-e))))
BG=Image.open(S+"/work/bggraded.png").convert("RGB")
BASE=ImageEnhance.Brightness(BG.filter(ImageFilter.GaussianBlur(42))).enhance(0.48).convert("RGBA")
def bgframe(t,dur,z0=1.0,z1=1.05):
    z=z0+(z1-z0)*t/max(dur,0.01); w,h=int(W*z),int(H*z); b=BASE.resize((w,h)); x,y=(w-W)//2,(h-H)//2; return b.crop((x,y,x+W,y+H))
def out(img,rgba=False): sys.stdout.buffer.write((img if rgba else img.convert("RGB")).tobytes())
def pill(c,box,p,outline=(255,255,255),fill=None,width=3,r=None):
    if p<=0: return
    o=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(o); a=int(255*min(1,p))
    d.rounded_rectangle(box,r or (box[3]-box[1])//2,outline=outline+(int(a*0.85),) if outline else None,fill=fill+(int(fill[3]*min(1,p)) if len(fill)==4 else a,) if fill and len(fill)==3 else (fill[:3]+(int(fill[3]*min(1,p)),) if fill else None),width=width)
    c.alpha_composite(o)
def mark(d,kind,cx,cy,r,col,w):
    if kind=="x": d.line((cx-r,cy-r,cx+r,cy+r),fill=col,width=w); d.line((cx-r,cy+r,cx+r,cy-r),fill=col,width=w)
    else: d.line((cx-r,cy,cx-r*0.3,cy+r*0.7,cx+r,cy-r*0.8),fill=col,width=w,joint="curve")
RED=(214,69,65); GREEN=(39,160,105)

def intro(dur):
    l1=layer("მითია",KA(900,190),(255,255,255,255),shadow=150); l2=layer("თუ",KA(700,90),(255,255,255,215),shadow=150)
    l3=layer("რეალობა?",KA(900,150),(255,255,255,255),shadow=150); l4=layer("MYTH OR TRUTH?",EN(700,48),(255,255,255,235),spacing=8)
    f5=KA(700,46); l5=layer("ბოტოქსის ინექცია",f5,(255,255,255,255)); pw=tl("ბოტოქსის ინექცია",f5)/2+70
    for f in range(int(dur*FPS)):
        t=f/FPS; c=bgframe(t,dur)
        put(c,l1,W/2,700,t,0.1); put(c,l2,W/2,860,t,0.35); put(c,l3,W/2,1020,t,0.55)
        d=ImageDraw.Draw(c); hw=int(70*ease((t-0.9)/0.4))
        if hw>0: d.rounded_rectangle((W//2-hw,1150,W//2+hw,1156),3,fill=(255,255,255,230))
        put(c,l4,W/2,1230,t,1.0,dy=30); pill(c,(W/2-pw,1335,W/2+pw,1445),ease((t-1.3)/0.45)); put(c,l5,W/2,1390,t,1.3,dy=30)
        fo=ease((t-(dur-0.35))/0.35)  # no fade here; xfade handles transitions
        out(c)
def question(i,dur):
    q=Q[i]; fk=KA(900,74); lines=wrap(q["q_ka"],fk,900); lk=layer(lines,fk,(255,255,255,255),shadow=160,lh=1.25)
    fe=EN(600,42); le=layer(wrap(q["q_en"],fe,860),fe,(255,255,255,215),lh=1.3)
    hk=layer("მითია თუ რეალობა?",KA(800,40),(255,255,255,255)); he=layer("MYTH OR TRUTH?",EN(700,28),(255,255,255,200),spacing=6)
    ask=layer("შენი აზრით?",KA(700,40),(255,255,255,230)); 
    cm=layer("მითი",KA(800,50),(255,255,255,255)); cr=layer("რეალობა",KA(800,50),(255,255,255,255))
    hq=lk.height-80; top=960-hq/2-40
    for f in range(int(dur*FPS)):
        t=f/FPS*1.9; c=bgframe(f/FPS,dur,1.02,1.07)
        pill(c,(W/2-250,top-215,W/2+250,top-85),ease((t-0.05)/0.4),outline=(255,255,255),width=3)
        put(c,hk,W/2,top-168,t,0.05,dy=20); put(c,he,W/2,top-122,t,0.15,dy=20)
        put(c,lk,W/2,top+lk.height/2-40,t,0.3,dy=60)
        ey=top+hq+50; d=ImageDraw.Draw(c); hw=int(60*ease((t-0.7)/0.4))
        if hw>0: d.rounded_rectangle((W//2-hw,ey-3,W//2+hw,ey+3),3,fill=(255,255,255,200))
        put(c,le,W/2,ey+40+le.height/2-40,t,0.8,dy=30)
        by=min(1580,ey+le.height+175); put(c,ask,W/2,by,t,1.2,dy=20)
        for k,(lab,col,kind,x) in enumerate([(cm,RED,"x",W/2-200),(cr,GREEN,"v",W/2+200)]):
            p=(t-1.4-0.12*k)/0.45
            if p>0:
                s=back(p); bw,bh=int(330*s),int(110*s)
                o=Image.new("RGBA",(W,H),(0,0,0,0)); dd=ImageDraw.Draw(o)
                pulse=1+0.04*math.sin((t-1.9)*5) if t>1.9 else 1
                bw,bh=int(bw*pulse),int(bh*pulse)
                dd.rounded_rectangle((x-bw/2,by+135-bh/2,x+bw/2,by+135+bh/2),bh//2,fill=col+(int(225*min(1,p)),))
                c.alpha_composite(o)
                L2=lab.resize((max(1,int(lab.width*s*pulse)),max(1,int(lab.height*s*pulse))))
                c.alpha_composite(L2,(int(x-L2.width/2),int(by+135-L2.height/2-6*s)))
        out(c)
def outro(dur):
    l1=layer("გამოიწერე",KA(900,140),(255,255,255,255),shadow=150)
    l2=layer(["მეტი სასარგებლო","ინფორმაციისთვის"],KA(700,58),(255,255,255,230),shadow=120,lh=1.25)
    l3=layer("FOLLOW FOR MORE",EN(800,46),(255,255,255,235),spacing=8)
    fb=EN(800,48)
    for f in range(int(dur*FPS)):
        t=f/FPS; c=bgframe(t,dur)
        put(c,l1,W/2,720,t,0.1); put(c,l2,W/2,900,t,0.35); put(c,l3,W/2,1060,t,0.6,dy=30)
        p=(t-0.9)/0.5
        if p>0:
            pressed=t>1.9; s=back(p)*(0.94 if 1.9<t<2.1 else 1)
            col=(255,255,255) if pressed else (0,149,246); txt="Following ✓" if False else ("Following" if pressed else "Follow")
            bw,bh=int(420*s),int(120*s); o=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(o)
            d.rounded_rectangle((W/2-bw/2,1260-bh/2,W/2+bw/2,1260+bh/2),26,fill=col+(int(255*min(1,p)),))
            c.alpha_composite(o); L=layer(txt,EN(800,int(48*s)),(30,30,30,255) if pressed else (255,255,255,255)); c.alpha_composite(L,(int(W/2-L.width/2),int(1260-L.height/2-4)))
            if pressed:
                r=ease((t-1.9)/0.5); o=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(o)
                rr=int(240+160*r); d.ellipse((W/2-rr,1260-rr*0.45,W/2+rr,1260+rr*0.45),outline=(255,255,255,int(160*(1-r))),width=4); c.alpha_composite(o)
        out(c)
def stamp(verdict,dur,t_in):
    # RGBA overlay 1080x560 placed at y=110; pops big then settles as a badge
    col=RED if verdict=="myth" else GREEN; ka="მითი" if verdict=="myth" else "რეალობა"; en="MYTH" if verdict=="myth" else "TRUTH"
    lk=layer(ka,KA(900,96),(255,255,255,255)); le=layer(en,EN(800,40),(255,255,255,235),spacing=10)
    bw=max(lk.width,le.width)-80+150+110; bh=230
    st=Image.new("RGBA",(bw+40,bh+40),(0,0,0,0)); d=ImageDraw.Draw(st)
    d.rounded_rectangle((20,20,20+bw,20+bh),46,fill=col+(240,)); d.rounded_rectangle((32,32,8+bw,8+bh),38,outline=(255,255,255,170),width=4)
    mark(d,"x" if verdict=="myth" else "v",20+85,20+bh/2,34,(255,255,255,255),16)
    tx=20+150+(bw-150-110)/2+40
    st.alpha_composite(lk,(int(tx-lk.width/2),int(20+bh/2-lk.height/2-40+6))); st.alpha_composite(le,(int(tx-le.width/2),int(20+bh/2-le.height/2+70)))
    sh=Image.new("RGBA",(st.width+80,st.height+80),(0,0,0,0)); m=st.getchannel("A").point(lambda v:int(v*0.45)); sh.paste((0,0,0,255),(40,50),m); sh=sh.filter(ImageFilter.GaussianBlur(18)); sh.alpha_composite(st,(40,40)); st=sh
    OH=560
    for f in range(int(dur*FPS)):
        t=f/FPS-t_in; c=Image.new("RGBA",(W,OH),(0,0,0,0))
        if t>0:
            if t<0.5: s=1.25*back(t/0.5); rot=-8*(1-ease(t/0.5))-4; a=min(1,t/0.15)
            else:
                p=ease((t-1.6)/0.5); s=1.25-0.6*p; rot=-4+4*p; a=1
            if t>1.6: cy=280-170*ease((t-1.6)/0.5)
            else: cy=280
            L=st.resize((max(1,int(st.width*s)),max(1,int(st.height*s))),Image.LANCZOS).rotate(rot,expand=True,resample=Image.BICUBIC)
            if a<1: L.putalpha(L.getchannel("A").point(lambda v:int(v*a)))
            c.alpha_composite(L,(int(W/2-L.width/2),int(cy-L.height/2)))
        out(c,rgba=True)
kind=sys.argv[2]
if kind=="intro": intro(float(sys.argv[3]))
elif kind=="question": question(int(sys.argv[3]),float(sys.argv[4]))
elif kind=="outro": outro(float(sys.argv[3]))
elif kind=="stamp": stamp(sys.argv[3],float(sys.argv[4]),float(sys.argv[5]))
