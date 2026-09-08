"""Add a '<48 hours' chip, filter and stat to the board template."""
import io

p = 'template.html'
s = io.open(p, encoding='utf-8').read()
n = 0

# 1. chip style - its own colour so it reads as the newest thing on the page
old = '.chip.soft{background:var(--warn-bg); color:var(--warn)}'
new = (old + '\n.chip.new48{background:var(--live); color:var(--on-accent); '
             'letter-spacing:.08em}')
if '.chip.new48' not in s:
    s = s.replace(old, new, 1); n += 1

# 2. filter button, placed first so it is the first thing reachable
old = '      <button class="f" data-f="chi" aria-pressed="false">Chicago</button>'
new = ('      <button class="f" data-f="new48" aria-pressed="false">New &lt;48h</button>\n' + old)
if 'data-f="new48"' not in s:
    s = s.replace(old, new, 1); n += 1

# 3. render the chip FIRST in the list so it leads the row
old = "  if(d.chi) chips.push('<span class=\"chip chi\">Chicago</span>');"
new = ("  if(d.new48) chips.push('<span class=\"chip new48\">&lt;48 hours</span>');\n" + old)
if 'chip new48' not in s:
    s = s.replace(old, new, 1); n += 1

# 4. filter predicate
old = "  if(active==='pay' && !(d.smax>=150000)) return false;"
new = "  if(active==='new48' && !d.new48) return false;\n" + old
if "active==='new48'" not in s:
    s = s.replace(old, new, 1); n += 1

io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('template.html: %d edits' % n)

# 5. inject.py must emit the flag
p = 'inject.py'
s = io.open(p, encoding='utf-8').read()
old = "        roles=r.get('n_roles', 1), loc=_locchip(r), soft=soft_pay(r),"
new = ("        roles=r.get('n_roles', 1), loc=_locchip(r), soft=soft_pay(r),\n"
       "        new48=bool(r.get('new48')),")
if 'new48=bool' not in s:
    assert old in s
    s = s.replace(old, new, 1)
    io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
    print('inject.py: emits new48')
else:
    print('inject.py: already emits new48')
