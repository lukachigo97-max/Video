import sys, json, wave, numpy as np
from faster_whisper import WhisperModel
def load(f):
    w=wave.open(f); return np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
def chunks(a, sr=16000, lo=3.0, hi=5.5):
    fr=int(0.02*sr); e=np.array([np.sqrt(np.mean(a[i:i+fr]**2)) for i in range(0,len(a)-fr,fr)])
    cuts=[0]; 
    while (len(e)-cuts[-1])*0.02>hi:
        s=cuts[-1]+int(lo/0.02); t=cuts[-1]+int(hi/0.02); cuts.append(s+int(np.argmin(e[s:t])))
    cuts.append(len(e)); return [(c*0.02) for c in cuts]
m = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=4)
out={}
for i in range(1,5):
    a=load(f"{sys.argv[1]}/c{i}.wav"); cs=chunks(a); out[i]=[]
    print(f"== clip {i}", flush=True)
    for s,t in zip(cs,cs[1:]):
        seg=a[int(s*16000):int(t*16000)]
        segs,_=m.transcribe(seg, language="ka", beam_size=5, condition_on_previous_text=False, vad_filter=False, without_timestamps=True)
        txt=" ".join(x.text.strip() for x in segs)
        out[i].append([round(s,2),round(t,2),txt]); print(f"[{s:5.2f}-{t:5.2f}] {txt}", flush=True)
json.dump(out, open(f"{sys.argv[1]}/transcript2.json","w"), ensure_ascii=False, indent=1)
