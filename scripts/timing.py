import sys, json, wave, numpy as np
sys.path.insert(0, sys.argv[1]+"/scripts"); from content import Q
A=sys.argv[1]+"/audio/"
def load(f):
    w=wave.open(f); return np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
res=[]
for qi,q in enumerate(Q):
    a=load(A+f"c{q['clip']}.wav"); fr=320; e=np.array([np.sqrt(np.mean(a[i:i+fr]**2)) for i in range(0,len(a)-fr,fr)])
    edb=20*np.log10(e+1e-9); thr=max(edb.max()-32,-45); voiced=edb>thr
    # close tiny gaps (<0.12s), so only real pauses count as silence
    v=voiced.copy(); n=len(v); i=0
    while i<n:
        if not v[i]:
            j=i
            while j<n and not v[j]: j+=1
            if (j-i)*0.02<0.18 and i>0 and j<n: v[i:j]=True
            i=j
        else: i+=1
    words=[]
    for (s,t,txt) in q["chunks"]:
        ws=txt.split(); idx=[k for k in range(int(s/0.02),min(n,int(t/0.02))) if v[k]]
        if not idx: continue
        wts=np.array([len(w)+2 for w in ws],float); cum=np.concatenate([[0],np.cumsum(wts)])/wts.sum()
        for k,w in enumerate(ws):
            a0=idx[min(len(idx)-1,int(cum[k]*len(idx)))]*0.02; a1=idx[min(len(idx)-1,int(cum[k+1]*len(idx))-1)]*0.02+0.02
            words.append((w,a0,a1))
    out=[]; wi=0
    for ka,en in q["phrases"]:
        k=len(ka.split()); seg=words[wi:wi+k]; assert [x[0] for x in seg]==ka.split(),(qi,ka,[x[0] for x in seg]); wi+=k
        out.append(dict(ka=ka,en=en,start=seg[0][1],end=seg[-1][2]))
    assert wi==len(words)
    res.append(out)
    for p in out: print(qi, f"{p['start']:5.2f}-{p['end']:5.2f}", p['ka'])
json.dump(res,open(sys.argv[1]+"/work/captions.json","w"),ensure_ascii=False,indent=1)
