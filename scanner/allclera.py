import json, re, sal

for r in json.load(open('scan_api.json', encoding='utf-8')):
    if (r.get('company') or '').lower() != 'clera':
        continue
    print('board token:', r.get('token'), '| ats:', r.get('ats'), '| jobs:', len(r.get('jobs', [])))
    for j in r.get('jobs', []):
        print('  %-48s smin=%-8s smax=%-8s %s' % (
            (j.get('title') or '')[:48], j.get('smin'), j.get('smax'), j.get('opened')))
        if (j.get('smax') or 0) >= 300000:
            t = (j.get('desc') or '').replace('\n', ' ')
            print('     extract on stored desc:', sal.extract(t))
            for m in list(re.finditer(r'.{0,90}\$[\d][\d,.]*.{0,70}', t))[:4]:
                print('     ...' + re.sub(r'\s+', ' ', m.group(0)).strip()[:180])
