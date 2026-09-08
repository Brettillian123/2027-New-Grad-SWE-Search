import json,sys,urllib.request,concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
U={"greenhouse":"https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
   "ashby":"https://api.ashbyhq.com/posting-api/job-board/{t}",
   "lever":"https://api.lever.co/v0/postings/{t}?mode=json"}
def probe(a,t):
    try:
        r=urllib.request.Request(U[a].format(t=t),headers=UA)
        with urllib.request.urlopen(r,timeout=12) as f:
            d=json.loads(f.read().decode("utf-8","replace"))
        n=len(d) if isinstance(d,list) else len(d.get("jobs",[]))
        return (a,t,n) if n>0 else None
    except Exception: return None
toks=[l.strip() for l in open(sys.argv[1]) if l.strip()]
ats=sys.argv[2].split(",")
jobs=[(a,t) for a in ats for t in toks]
found=[]
with cf.ThreadPoolExecutor(max_workers=48) as ex:
    for i,r in enumerate(ex.map(lambda x:probe(*x), jobs)):
        if r: found.append(r); print(f"{r[0]} {r[1]} {r[2]}",flush=True)
print(f"# {len(found)} boards from {len(jobs)} probes",file=sys.stderr)
