import json, re, sal

for r in json.load(open('scan_new.json', encoding='utf-8')):
    for j in r.get('jobs', []):
        if 'NTT' in (j.get('company') or '') and 'Junior' in j.get('title', ''):
            print('title :', j['title'], '| loc:', j.get('loc'))
            print('stored:', j.get('smin'), j.get('smax'))
            t = (j.get('desc') or '').replace('\n', ' ')
            print('extract:', sal.extract(t))
            for m in list(re.finditer(r'.{0,80}\$[\d][\d,.]*.{0,60}', t))[:3]:
                print('   ...' + re.sub(r'\s+', ' ', m.group(0)).strip()[:170])
            raise SystemExit
print('not found')
