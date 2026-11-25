import sys, json, subprocess, os
S=sys.argv[1]; sys.path.insert(0,S+"/scripts"); from content import Q
WK=S+"/work/"; os.makedirs(WK+"seg",exist_ok=True); CAP=json.load(open(WK+"captions.json"))
GFX=["python3","-I",S+"/scripts/gfx.py",S]
ENC=["-c:v","libx264","-preset","medium","-crf","17","-pix_fmt","yuv420p","-r","30"]
def sh(cmd): subprocess.run(cmd,shell=True,check=True,executable="/bin/bash")
def card(args,outf,dur):
    sh(" ".join(GFX+args)+f" 2>/dev/null | ffmpeg -v error -y -f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 30 -i - "+" ".join(ENC)+f" {outf}")
QDUR=[4.6,5.0,5.6,6.0]; segs=[]
card(["intro","3.0"],WK+"seg/00_intro.mp4",3.0); segs.append((WK+"seg/00_intro.mp4",3.0,False))
def ts(t): h=int(t//3600); m=int(t%3600//60); s=t%60; return f"{h}:{m:02d}:{s:05.2f}"
for i,q in enumerate(Q):
    qf=WK+f"seg/{i+1}a_q.mp4"; card(["question",str(i),str(QDUR[i])],qf,QDUR[i]); segs.append((qf,QDUR[i],False))
    t0,t1=q["trim"]; D=t1-t0; caps=CAP[i]; tin=max(0.05,caps[0]["start"]-t0)
    st=WK+f"seg/{i+1}b_stamp.mov"
    sh(" ".join(GFX+["stamp",q["verdict"],f"{D:.2f}",f"{tin:.2f}"])+f" 2>/dev/null | ffmpeg -v error -y -f rawvideo -pix_fmt rgba -s 1080x560 -r 30 -i - -c:v qtrle {st}")
    ass=WK+f"seg/{i+1}b.ass"
    with open(ass,"w") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Cap,Noto Sans Georgian ExtraBold,70,&H00FFFFFF,&H00FFFFFF,&H00141414,&H96000000,0,0,0,0,100,100,0,0,1,3.2,2.5,8,90,90,1215,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for k,c in enumerate(caps):
            a=max(0,c["start"]-t0-0.05); b=(caps[k+1]["start"]-t0-0.05) if k+1<len(caps) else min(D,c["end"]-t0+0.5)
            b=max(b,a+0.6)
            txt=c["ka"]+r"\N{\fnMontserrat SemiBold\fs52\c&H00E6F5FF&\bord2.6\shad2}"+c["en"]
            f.write(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{{\\fad(90,60)\\t(0,140,\\fscx100\\fscy100)\\fscx94\\fscy94}}{txt}\n")
    af=WK+f"seg/{i+1}b_ans.mp4"
    vf=(f"[0:v]scale=w='2*trunc(540*(1+0.04*t/{D:.2f}))':h=-2:eval=frame:flags=bicubic,crop=1080:1920,"
        f"ass={ass}:fontsdir={S}/fonts[v];[v][1:v]overlay=0:110:shortest=0:eof_action=pass,format=yuv420p[vo]")
    sh(f"ffmpeg -v error -y -ss {t0} -t {D:.2f} -i {WK}base{q['clip']}.mp4 -i {st} -filter_complex \"{vf}\" -map [vo] -map 0:a "+" ".join(ENC)+
       f" -af 'afade=t=in:d=0.08,afade=t=out:st={D-0.25:.2f}:d=0.25' -c:a aac -b:a 192k -ar 48000 -ac 2 {af}")
    segs.append((af,D,True))
card(["outro","3.2"],WK+"seg/99_outro.mp4",3.2); segs.append((WK+"seg/99_outro.mp4",3.2,False))
# assemble with crossfades
X=0.35; inputs=" ".join(f"-i {p}" for p,_,_ in segs); fc=[]; prev="[0:v]"; off=0; starts=[0]
for k in range(1,len(segs)):
    off+=segs[k-1][1]-X; starts.append(off); fc.append(f"{prev}[{k}:v]xfade=transition=fade:duration={X}:offset={off:.3f}[x{k}]"); prev=f"[x{k}]"
total=off+segs[-1][1]; am=[]
for k,(p,d,has) in enumerate(segs):
    if has: ms=int(starts[k]*1000); fc.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]"); am.append(f"[a{k}]")
fc.append("".join(am)+f"amix=inputs={len(am)}:normalize=0,apad,atrim=0:{total:.3f}[ao]")
json.dump(dict(segs=[(os.path.basename(p),d,s) for (p,d,_),s in zip(segs,starts)],total=total),open(WK+"timeline.json","w"),indent=1)
sh(f"ffmpeg -v error -y {inputs} -filter_complex \"{';'.join(fc)}\" -map {prev} -map [ao] -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 192k -movflags +faststart {WK}final.mp4")
print("total",total)
