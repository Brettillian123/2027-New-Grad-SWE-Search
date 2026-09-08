"""Set a remote flag from the FULL description before it is truncated.

Descriptions are cut to 1500 chars at collection. Empower's "Workplace
flexibility: Remote - Nationwide" sits far deeper than that, so by gating time
the evidence is already gone - the same failure mode as the salary truncation.
"""
import io

PATCHES = [
    # ats.py - alongside the salary extraction, which already reads the full text
    ('ats.py',
     '        h["desc"] = (h.get("desc") or "")[:1500]\n        hits.append(h)',
     '        try:\n'
     '            import geo as _geo\n'
     '            h["remote_body"] = _geo.remote_in_text(j.get("desc") or "")\n'
     '        except Exception:\n'
     '            pass\n'
     '        h["desc"] = (h.get("desc") or "")[:1500]\n        hits.append(h)'),
    # wd3 / wd4 - the detail fetch holds the full description in `desc`
    ('wd3.py',
     '            j.update(tier=tier, floor=floor, stretch=stretch)\n'
     '            j["desc"] = j["desc"][:1500]',
     '            j.update(tier=tier, floor=floor, stretch=stretch)\n'
     '            try:\n'
     '                import geo as _geo\n'
     '                j["remote_body"] = _geo.remote_in_text(j.get("desc") or "")\n'
     '            except Exception:\n'
     '                pass\n'
     '            j["desc"] = j["desc"][:1500]'),
    ('wd4.py',
     '                j.update(tier=tier, floor=floor, stretch=stretch)\n'
     '                j["desc"] = j["desc"][:1500]',
     '                j.update(tier=tier, floor=floor, stretch=stretch)\n'
     '                try:\n'
     '                    import geo as _geo\n'
     '                    j["remote_body"] = _geo.remote_in_text(j.get("desc") or "")\n'
     '                except Exception:\n'
     '                    pass\n'
     '                j["desc"] = j["desc"][:1500]'),
    ('sweep_new.py',
     "        j['desc'] = (j.get('desc') or '')[:1500]\n        hits.append(j)",
     "        try:\n"
     "            import geo as _geo\n"
     "            j['remote_body'] = _geo.remote_in_text(j.get('desc') or '')\n"
     "        except Exception:\n"
     "            pass\n"
     "        j['desc'] = (j.get('desc') or '')[:1500]\n        hits.append(j)"),
]

for f, old, new in PATCHES:
    s = io.open(f, encoding='utf-8').read()
    if 'remote_body' in s:
        print('%-14s already wired' % f)
        continue
    if old not in s:
        print('%-14s ANCHOR NOT FOUND' % f)
        continue
    io.open(f, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new, 1))
    print('%-14s wired' % f)

# refresh.py - honour the flag in the gate
s = io.open('refresh.py', encoding='utf-8').read()
old = """        if not (g['remote'] or g['chicago']):
            f['not remote/Chicago'] += 1
            continue"""
new = """        # A posting whose location names an office can still BE remote; the
        # collectors set remote_body from the full text before truncation.
        body_remote = bool(j.get('remote_body'))
        if not (g['remote'] or g['chicago'] or body_remote):
            f['not remote/Chicago'] += 1
            continue"""
if 'body_remote' in s:
    print('refresh.py    already honours the flag')
elif old in s:
    s = s.replace(old, new, 1)
    s = s.replace("                 new48=(op >= NEW48.isoformat()))",
                  "                 new48=(op >= NEW48.isoformat()))\n"
                  "        if body_remote:\n"
                  "            j['remote'] = True", 1)
    io.open('refresh.py', 'w', encoding='utf-8', newline='\n').write(s)
    print('refresh.py    gate now honours remote_body')
else:
    print('refresh.py    ANCHOR NOT FOUND')
