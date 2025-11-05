#!/usr/bin/env python3
"""
collect_metrics.py — Phase 1 baseline metric extraction
Usage:
    python3 collect_metrics.py server_log.txt client1_log.txt client2_log.txt ...
Output:
    metrics.csv with columns:
    client_id, snapshot_id, seq_num, server_timestamp_ms, recv_time_ms, latency_ms, jitter_ms
"""

import sys, re, csv, statistics

if len(sys.argv) < 3:
    print("Usage: python3 collect_metrics.py server_log.txt client1_log.txt ...")
    sys.exit(1)

server_log = sys.argv[1]
client_logs = sys.argv[2:]
rows = []

pattern = re.compile(
    r"SNAPSHOT.*recv_time=(?P<recv>\d+\.\d+)\s+server_ts=(?P<srv>\d+\.\d+)\s+snapshot_id=(?P<snap>\d+)\s+seq=(?P<seq>\d+)"
)

for cfile in client_logs:
    cid_match = re.search(r"client(\d+)_log", cfile)
    cid = int(cid_match.group(1)) if cid_match else 0
    last_latency = None
    with open(cfile) as f:
        for line in f:
            m = pattern.search(line)
            if m:
                recv = float(m.group("recv"))
                srv = float(m.group("srv"))
                latency = (recv - srv) * 1000.0
                jitter = abs(latency - last_latency) if last_latency else 0.0
                last_latency = latency
                rows.append({
                    "client_id": cid,
                    "snapshot_id": int(m.group("snap")),
                    "seq_num": int(m.group("seq")),
                    "server_timestamp_ms": srv * 1000.0,
                    "recv_time_ms": recv * 1000.0,
                    "latency_ms": latency,
                    "jitter_ms": jitter
                })

if not rows:
    print("[collect_metrics] No valid snapshot lines found in logs.")
    sys.exit(0)

out_csv = "metrics.csv"
with open(out_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

lat = [r["latency_ms"] for r in rows]
jit = [r["jitter_ms"] for r in rows]

print(f"[collect_metrics] {len(rows)} samples → {out_csv}")
print(f"Latency (ms): mean={statistics.mean(lat):.2f}, stdev={statistics.stdev(lat):.2f}")
print(f"Jitter (ms):  mean={statistics.mean(jit):.2f}, stdev={statistics.stdev(jit):.2f}")