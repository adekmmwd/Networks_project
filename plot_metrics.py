#!/usr/bin/env python3
"""
collect_metrics.py — Phase 1 baseline metric extraction + performance metrics

Usage:
    python3 collect_metrics.py server_log.txt client1_log.txt client2_log.txt ...
Outputs:
    metrics.csv  (per-snapshot latency/jitter)
    collect_metrics_summary.txt  (summary for plotting)
"""

import sys, re, csv, statistics, time, threading, psutil
import pandas as pd

if len(sys.argv) < 3:
    print("Usage: python3 collect_metrics.py server_log.txt client1_log.txt ...")
    sys.exit(1)

server_log = sys.argv[1]
client_logs = sys.argv[2:]
rows = []

pattern = re.compile(
    r"SNAPSHOT.*recv_time=(?P<recv>\d+\.\d+)\s+server_ts=(?P<srv>\d+\.\d+)\s+snapshot_id=(?P<snap>\d+)\s+seq=(?P<seq>\d+)"
)

# ---------------------------
# CPU monitoring thread
# ---------------------------
cpu_samples = []
stop_flag = threading.Event()

def monitor_cpu():
    while not stop_flag.is_set():
        cpu_samples.append(psutil.cpu_percent(interval=0.5))

t = threading.Thread(target=monitor_cpu, daemon=True)
t.start()

# ---------------------------
# Parse client logs
# ---------------------------
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

# ---------------------------
# Stop CPU monitor
# ---------------------------
stop_flag.set()
t.join()

if not rows:
    print("[collect_metrics] No valid snapshot lines found in logs.")
    sys.exit(0)

# ---------------------------
# Write metrics.csv
# ---------------------------
out_csv = "metrics.csv"
with open(out_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

# ---------------------------
# Compute statistics
# ---------------------------
lat = [r["latency_ms"] for r in rows]
jit = [r["jitter_ms"] for r in rows]
print(f"[collect_metrics] {len(rows)} samples → {out_csv}")
print(f"Latency (ms): mean={statistics.mean(lat):.2f}, stdev={statistics.stdev(lat):.2f}")
print(f"Jitter  (ms): mean={statistics.mean(jit):.2f}, stdev={statistics.stdev(jit):.2f}")

# ---------------------------
# Update rate per client
# ---------------------------
df = pd.DataFrame(rows)
rates = []
for cid, group in df.groupby("client_id"):
    tmin = group["server_timestamp_ms"].min()
    tmax = group["server_timestamp_ms"].max()
    if tmax > tmin:
        rate = len(group) / ((tmax - tmin) / 1000.0)
        rates.append((cid, rate))

if rates:
    print("\n=== Update rate per client (snapshots/sec) ===")
    for cid, rps in rates:
        print(f"Client {cid}: {rps:.2f} updates/sec")
    avg_rate = sum(r for _, r in rates) / len(rates)
else:
    avg_rate = 0.0

# ---------------------------
# Average CPU usage
# ---------------------------
avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
print(f"\nAverage update rate: {avg_rate:.2f} updates/sec/client")
print(f"Average CPU usage:   {avg_cpu:.2f}%")

# ---------------------------
# Performance goal summary
# ---------------------------
if avg_rate >= 20 and statistics.mean(lat) <= 50 and avg_cpu < 60:
    print("\n✅ Performance goal met: ≥20 updates/sec per client, latency ≤50 ms, CPU < 60%")
else:
    print("\n⚠ Performance goal not met.")
    print(f"   Target: ≥20 updates/sec/client, latency ≤50 ms, CPU < 60%")

# ---------------------------
# Save summary for plotting
# ---------------------------
with open("collect_metrics_summary.txt", "w") as f:
    f.write(f"Latency mean: {statistics.mean(lat):.2f} ms\n")
    f.write(f"Jitter mean: {statistics.mean(jit):.2f} ms\n")
    for cid, rps in rates:
        f.write(f"Client {cid}: {rps:.2f} updates/sec\n")
    f.write(f"Average CPU usage: {avg_cpu:.2f}\n")

print("\n[collect_metrics] ✅ Saved summary to collect_metrics_summary.txt")