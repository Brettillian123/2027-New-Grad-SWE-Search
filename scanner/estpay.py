import re
NUM = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})?)(?:\.\d+)?\s?([kK])?")

def parse_max(text):
    """Top of a free-text pay string like '$235,000 - $300,000' or '~$110k-$120k'.
    Returns None when no usable figure is present."""
    if not text:
        return None
    t = str(text)
    if re.search(r"(not (published|disclosed)|unknown|n/?a\b|peer|undisclosed)", t, re.I) \
       and not NUM.search(t):
        return None
    vals = []
    for m in NUM.finditer(t):
        raw = m.group(1).replace(',', '')
        n = int(raw)
        if m.group(2) or n < 1000:
            n *= 1000
        if 20000 <= n <= 900000:
            vals.append(n)
    return max(vals) if vals else None

def parse_range(text):
    """(low, high) from a free-text pay string; (None, None) when unusable."""
    if not text:
        return (None, None)
    t = str(text)
    vals = []
    for m in NUM.finditer(t):
        n = int(m.group(1).replace(',', ''))
        if m.group(2) or n < 1000:
            n *= 1000
        if 20000 <= n <= 900000:
            vals.append(n)
    if not vals:
        return (None, None)
    return (min(vals), max(vals))
