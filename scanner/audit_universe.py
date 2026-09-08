"""Are we missing POSTINGS, or missing COMPANIES?

We scan 3,680 boards discovered from one aggregator dump plus name-guessing.
Greenhouse/Ashby/Lever have far more customers than that. This checks a list of
companies that demonstrably hire remote US engineers against our token set."""
import json, os, sys

known = [
    # remote-friendly tech that hires early-career
    'stripe', 'figma', 'notion', 'airtable', 'asana', 'atlassian', 'databricks',
    'snowflake', 'confluent', 'hashicorp', 'datadog', 'twilio', 'shopify',
    'coinbase', 'robinhood', 'plaid', 'brex', 'ramp', 'gusto', 'rippling',
    'deel', 'remote', 'oyster', 'zapier', 'automattic', 'gitlab', 'grafana',
    'sentry', 'vercel', 'netlify', 'render', 'fly', 'planetscale', 'supabase',
    'clickhouse', 'cockroachlabs', 'timescale', 'redpanda', 'temporal',
    'doordash', 'instacart', 'lyft', 'affirm', 'chime', 'betterment',
    'wealthfront', 'carta', 'mercury', 'anthropic', 'openai', 'scale',
    'huggingface', 'weightsandbiases', 'replicate', 'modal', 'together',
    'perplexity', 'cohere', 'runwayml', 'elevenlabs', 'sierra', 'harvey',
    'glean', 'writer', 'abridge', 'tempus', 'benchling', 'recursion',
    'flexport', 'samsara', 'verkada', 'rippling', 'attentive', 'klaviyo',
    'amplitude', 'mixpanel', 'segment', 'heap', 'fullstory', 'launchdarkly',
    'split', 'statsig', 'optimizely', 'contentful', 'sanity', 'storyblok',
]

toks = set()
names = set()
for f in ('rescan_nonwd.json', 'wd_targets_full.json'):
    if not os.path.exists(f):
        continue
    for t in json.load(open(f, encoding='utf-8')):
        tok = (t.get('token') or '').lower()
        toks.add(tok)
        toks.add(tok.split('|')[1] if '|' in tok else tok)
        names.add((t.get('company') or '').lower().replace(' ', ''))

have, miss = [], []
for k in sorted(set(known)):
    if k in toks or k in names or any(k in x for x in toks):
        have.append(k)
    else:
        miss.append(k)

print('checked %d well-known remote-hiring companies' % len(set(known)))
print('  in our token set : %d' % len(have))
print('  NOT in it        : %d' % len(miss))
print()
print('missing:')
for i in range(0, len(miss), 6):
    print('   ' + '  '.join('%-16s' % m for m in miss[i:i + 6]))
