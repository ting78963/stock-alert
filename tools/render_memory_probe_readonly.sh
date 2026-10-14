#!/usr/bin/env bash
# READ ONLY: /proc and cgroup metrics; no API, no LINE, no production writes.
set -u
interval="${1:-5}"
samples="${2:-720}"
if ! [[ "$interval" =~ ^[0-9]+$ && "$samples" =~ ^[0-9]+$ ]] || ((interval<1 || samples<1)); then
  echo "Usage: bash render_memory_probe_readonly.sh [interval_seconds>=1] [samples>=1]" >&2
  exit 2
fi
printf 'timestamp_utc,role,pid,ppid,rss_kib,hwm_kib,threads,cmd,cgroup_current_bytes,cgroup_peak_bytes,cgroup_max_bytes,oom_kill\n'
for ((i=0;i<samples;i++)); do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  current="$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo NA)"
  peak="$(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo NA)"
  limit="$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo NA)"
  oom="$(awk '$1=="oom_kill"{print $2}' /sys/fs/cgroup/memory.events 2>/dev/null)"
  oom="${oom:-NA}"
  found=0
  for dir in /proc/[0-9]*; do
    pid="${dir##*/}"
    [[ -r "$dir/cmdline" && -r "$dir/status" ]] || continue
    cmd="$(tr '\0' ' ' < "$dir/cmdline" 2>/dev/null || true)"
    [[ "$cmd" == *python* ]] || continue
    role=other_python
    [[ "$cmd" == *production_worker_v1.py* ]] && role=B_main
    [[ "$cmd" == *fugle_a_scanner_v2_4.py* ]] && role=A_scanner
    pp="$(awk '/^PPid:/{print $2}' "$dir/status" 2>/dev/null)"
    rss="$(awk '/^VmRSS:/{print $2}' "$dir/status" 2>/dev/null)"
    hwm="$(awk '/^VmHWM:/{print $2}' "$dir/status" 2>/dev/null)"
    threads="$(awk '/^Threads:/{print $2}' "$dir/status" 2>/dev/null)"
    cmd="${cmd//,/;}"
    printf '%s,%s,%s,%s,%s,%s,%s,"%s",%s,%s,%s,%s\n' "$ts" "$role" "$pid" "${pp:-NA}" "${rss:-NA}" "${hwm:-NA}" "${threads:-NA}" "$cmd" "$current" "$peak" "$limit" "$oom"
    found=1
  done
  if ((found==0)); then
    printf '%s,none,NA,NA,NA,NA,NA,"",%s,%s,%s,%s\n' "$ts" "$current" "$peak" "$limit" "$oom"
  fi
  if ((i+1<samples)); then sleep "$interval"; fi
done
