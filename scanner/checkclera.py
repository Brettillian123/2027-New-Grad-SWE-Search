import json, re, sal

for r in json.load(open('scan_api.json', encoding='utf-8')):
    for j in r.get('jobs', []):
        if 'clera' in (j.get('company') or '').lower():
            print('company:', j.get('company'), '| ats:', j.get('ats'))
            print('title  :', j.get('title'))
            print('loc    :', j.get('loc'))
            print('stored :', j.get('smin'), j.get('smax'))
            t = (j.get('desc') or '').replace('\n', ' ')
            print('extract:', sal.extract(t))
            print('url    :', (j.get('url') or '')[:110])
            for m in list(re.finditer(r'.{0,90}\$[\d][\d,.]*.{0,70}', t))[:4]:
                print('   ...' + re.sub(r'\s+', ' ', m.group(0)).strip()[:180])
            raise SystemExit
print('not found')
