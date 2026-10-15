#!/usr/bin/env bash
# READ ONLY: /proc and cgroup metrics. No Fugle/FinMind/LINE/database calls.
# Single-instance, 7-hour default; output on persistent disk.
set -u
interval="${1:-5}"
samples="${2:-5040}"
if ! [[ "$interval" =~ ^[0-9]+$ && "$samples" =~ ^[0-9]+$ ]] || ((interval<1 || samples<1)); then
  echo "Usage: bash tools/render_memory_probe_readonly.sh [interval_seconds>=1] [samples>=1]" >&2
  exit 2
fi
outdir="${MEMORY_PROBE_OUTPUT_DIR:-/var/data/memory-diagnostics}"
mkdir -p "$outdir" || { echo "Cannot create output directory: $outdir" >&2; exit 1; }
command -v flock >/dev/null 2>&1 || { echo "STOP: flock unavailable; cannot guarantee single instance" >&2; exit 1; }
lock="$outdir/render_memory_probe.lock"
exec 9>"$lock"
if ! flock -n 9; then
  echo "[SKIP] Another memory probe is already running (lock: $lock)" >&2
  exit 0
fi
runid="$(date -u +%Y%m%dT%H%M%SZ)_$$"
outfile="$outdir/render_memory_probe_$runid.csv"
echo "[START] interval=${interval}s samples=$samples output=$outfile"
printf 'timestamp_utc,role,pid,ppid,rss_kib,hwm_kib,threads,cmd,cgroup_current_bytes,cgroup_peak_bytes,cgroup_max_bytes,oom_kill,anon_bytes,file_bytes,slab_bytes,kernel_bytes,inactive_file_bytes,active_file_bytes,memory_events_max,memory_events_oom\n' > "$outfile"
read_cgroup() {
  current="$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo NA)"
  peak="$(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo NA)"
  limit="$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo NA)"
  oom="$(awk '$1=="oom_kill"{print $2}' /sys/fs/cgroup/memory.events 2>/dev/null)"
  maxevents="$(awk '$1=="max"{print $2}' /sys/fs/cgroup/memory.events 2>/dev/null)"
  oomevents="$(awk '$1=="oom"{print $2}' /sys/fs/cgroup/memory.events 2>/dev/null)"
  oom="${oom:-NA}"; maxevents="${maxevents:-NA}"; oomevents="${oomevents:-NA}"
  anon=NA; file=NA; slab=NA; kernel=NA; inactive_file=NA; active_file=NA
  while read -r k v; do
    case "$k" in
      anon) anon="$v";; file) file="$v";; slab) slab="$v";; kernel) kernel="$v";;
      inactive_file) inactive_file="$v";; active_file) active_file="$v";;
    esac
  done < /sys/fs/cgroup/memory.stat
}
trap 'echo "[STOP] signal received; output=$outfile" >&2; exit 130' INT TERM
for ((i=0;i<samples;i++)); do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  read_cgroup
  found=0
  for dir in /proc/[0-9]*; do
    pid="${dir##*/}"
    [[ -r "$dir/cmdline" && -r "$dir/status" ]] || continue
    exe="$(readlink "$dir/exe" 2>/dev/null || true)"
    [[ "$exe" == *python* ]] || continue
    cmd="$(tr '\0' ' ' < "$dir/cmdline" 2>/dev/null || true)"
    role=other_python
    [[ "$cmd" == *production_worker_v1.py* || "$cmd" == *production_worker_v2_shared_ws.py* ]] && role=B_main
    [[ "$cmd" == *fugle_a_scanner_v2_4.py* ]] && role=A_scanner
    pp="$(awk '/^PPid:/{print $2}' "$dir/status" 2>/dev/null)"
    rss="$(awk '/^VmRSS:/{print $2}' "$dir/status" 2>/dev/null)"
    hwm="$(awk '/^VmHWM:/{print $2}' "$dir/status" 2>/dev/null)"
    threads="$(awk '/^Threads:/{print $2}' "$dir/status" 2>/dev/null)"
    cmd="${cmd//,/;}"
    cmd="${cmd//\"/\"\"}"
    printf '%s,%s,%s,%s,%s,%s,%s,"%s",%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$ts" "$role" "$pid" "${pp:-NA}" "${rss:-NA}" "${hwm:-NA}" "${threads:-NA}" "$cmd" "$current" "$peak" "$limit" "$oom" "$anon" "$file" "$slab" "$kernel" "$inactive_file" "$active_file" "$maxevents" "$oomevents" >> "$outfile"
    found=1
  done
  if ((found==0)); then
    printf '%s,none,NA,NA,NA,NA,NA,"",%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$ts" "$current" "$peak" "$limit" "$oom" "$anon" "$file" "$slab" "$kernel" "$inactive_file" "$active_file" "$maxevents" "$oomevents" >> "$outfile"
  fi
  if ((i+1<samples)); then sleep "$interval"; fi
done
echo "[DONE] samples=$samples output=$outfile"
