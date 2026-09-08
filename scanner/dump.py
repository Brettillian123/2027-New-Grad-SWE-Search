import json,sys,concurrent.futures as cf
from ats import FETCH
targets=json.load(open(sys.argv[1]))
def one(t):
    try:
        js=FETCH[t['ats']](t['token'])
        for j in js: j['company']=t['company']; j['_ats']=t['ats']
        return js
    except Exception as e:
        print('ERR',t['company'],t['ats'],str(e)[:60],file=sys.stderr); return []
out=[]
with cf.ThreadPoolExecutor(max_workers=14) as ex:
    for js in ex.map(one,targets): out+=js
json.dump(out,open(sys.argv[2],'w'))
print(len(out),'postings cached',file=sys.stderr)
