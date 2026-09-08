import json, urllib.request
from ats import UA

u = 'https://api.ashbyhq.com/posting-api/job-board/clera?includeCompensation=true'
d = json.loads(urllib.request.urlopen(
    urllib.request.Request(u, headers=UA), timeout=25).read().decode('utf-8', 'replace'))
for j in d.get('jobs', []):
    if j.get('title', '').strip().lower() == 'software engineer':
        print('title       :', j.get('title'))
        print('location    :', j.get('location'))
        print('published   :', j.get('publishedAt'))
        print('compensation:', json.dumps(j.get('compensation'), indent=1)[:900])
        break
else:
    print('role not on the live board any more')
