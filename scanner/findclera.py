import json, re, sal

for r in json.load(open('scan_api.json', encoding='utf-8')):
    for j in r.get('jobs', []):
        if 'clera' in (j.get('url') or ''):
            print('board company field:', repr(r.get('company')), '| job company:', repr(j.get('company')))
            print('title  :', j.get('title'))
            print('stored :', j.get('smin'), j.get('smax'))
            t = (j.get('desc') or '').replace('\n', ' ')
            print('extract on stored desc:', sal.extract(t))
            print('desc len:', len(t))
            for m in list(re.finditer(r'.{0,90}\$[\d][\d,.]*.{0,70}', t))[:5]:
                print('   ...' + re.sub(r'\s+', ' ', m.group(0)).strip()[:180])
            raise SystemExit
print('not found by url either')
