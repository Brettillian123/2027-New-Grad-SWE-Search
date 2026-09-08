#!/bin/bash
# probe.sh <ats> <token...>  -> prints token and job count if the board resolves
ats=$1; shift
for t in "$@"; do
  case $ats in
    gh) u="https://boards-api.greenhouse.io/v1/boards/$t/jobs";;
    lv) u="https://api.lever.co/v0/postings/$t?mode=json";;
    ab) u="https://api.ashbyhq.com/posting-api/job-board/$t";;
    sr) u="https://api.smartrecruiters.com/v1/companies/$t/postings?limit=1";;
  esac
  n=$(curl -s -m 12 "$u" | python -c "
import json,sys
try:
  d=json.load(sys.stdin)
  if isinstance(d,list): print(len(d))
  else: print(len(d.get('jobs',d.get('content',[]))))
except Exception: print(0)" 2>/dev/null)
  [ "$n" != "0" ] && [ -n "$n" ] && echo "$ats $t $n"
done
