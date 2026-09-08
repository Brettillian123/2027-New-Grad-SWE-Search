import json,sys,urllib.request,concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0","Accept":"application/json","Content-Type":"application/json"}
def probe(args):
    name,host,tenant,site=args
    try:
        r=urllib.request.Request(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
            data=json.dumps({"appliedFacets":{},"limit":1,"offset":0,"searchText":"software engineer"}).encode(),
            headers=UA)
        with urllib.request.urlopen(r,timeout=14) as f:
            d=json.loads(f.read().decode("utf-8","replace"))
        t=d.get("total",0)
        return (name,host,tenant,site,t) if t else None
    except Exception: return None
cands=[]
wd=json.load(open('auto_workday.json'))
for name,pairs in wd.items():
    for host,site in pairs:
        if 'myworkdayjobs.com' not in host: continue
        tenant=host.split('.')[0]
        for tn in {tenant, site.lower(), site.split('_')[0].lower()}:
            cands.append((name,host,tn,site))
cands=list(dict.fromkeys(cands))
print(len(cands),'workday candidates',file=sys.stderr)
ok=[]
with cf.ThreadPoolExecutor(max_workers=36) as ex:
    for r in ex.map(probe,cands):
        if r: ok.append(r); print('|'.join(map(str,r)),flush=True)
print(len(ok),'resolved',file=sys.stderr)
