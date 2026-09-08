#!/bin/bash
# wdprobe.sh  -- reads "name host tenant site" lines on stdin, prints those that resolve
while read -r name host tenant site; do
  [ -z "$name" ] && continue
  n=$(curl -s -m 15 -X POST "https://$host/wday/cxs/$tenant/$site/jobs" \
      -H "Content-Type: application/json" -H "Accept: application/json" \
      -H "User-Agent: Mozilla/5.0" -d '{"appliedFacets":{},"limit":1,"offset":0,"searchText":"software engineer"}' \
      | python -c "
import json,sys
try: print(json.load(sys.stdin).get('total',0))
except Exception: print(0)" 2>/dev/null)
  if [ -n "$n" ] && [ "$n" != "0" ]; then echo "$name|$host|$tenant|$site|$n"; fi
done
