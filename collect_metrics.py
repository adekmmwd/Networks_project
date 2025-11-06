#!/usr/bin/env python3
"""
collect_metrics.py — Phase 1 baseline metric extraction + performance metrics

Usage:
    python3 collect_metrics.py server_log.txt client1_log.txt client2_log.txt client3_log.txt client4_log.txt

Outputs:
    metrics.csv  with columns:
        client_id, snapshot_id, seq_num, server_timestamp_ms, recv_time_ms,
        latency_ms, jitter_ms
    collect_metrics_summary.txt  (for plotting)
Prints:
    - Avg latency, jitter
    - Cycles/sec per client
    - Average CPU usage
"""

import sys, re, csv, statistics, threading, psutil, pandas as pd

# ------------------------------------------------------------
# 1. Argument check (expect exactly 4 clients)
# ------------------------------------------------------------
if len(sys.argv) != 6:  # 1 script + 1 server log + 4 clients
    print("Usage: python3 collect_metrics.py server_log.txt client1_log.txt client2_log.txt client3_log.txt client4_log.txt")
    sys.exit(1)

server_log = sys.argv[1]
client_logs = sys.argv[2:]
rows = []

# Pattern to extract snapshot info
pattern = re.compile(
    r"SNAPSHOT.*recv_time=(?P<recv>\d+\.\d+)\s+server_ts=(?P<srv>\d+\.\d+)\s+snapshot_id=(?P<snap>\d+)\s+seq=(?P<seq>\d+)"
)

# ------------------------------------------------------------
# 2. CPU Monitoring Thread
# ------------------------------------------------------------
cpu_samples = []
stop_flag = threading.Event()

def monitor_cpu():
    while not stop_flag.is_set():
        cpu_samples.append(psutil.cpu_percent(interval=0.5))

t = threading.Thread(target=monitor_cpu, daemon=True)
t.start()

# ------------------------------------------------------------
# 3. Parse Client Logs
# ------------------------------------------------------------
for cfile in client_logs:
    # detect numeric ID from filename (any number)
    cid_match = re.search(r"(\d+)", cfile)
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

# ------------------------------------------------------------
# 4. Stop CPU monitor
# ------------------------------------------------------------
stop_flag.set()
t.join()

if not rows:
    print("[collect_metrics] No valid snapshot lines found in logs.")
    sys.exit(0)

# ------------------------------------------------------------
# 5. Write metrics.csv
# ------------------------------------------------------------
out_csv = "metrics.csv"
with open(out_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

# ------------------------------------------------------------
# 6. Compute Latency/Jitter Stats
# ------------------------------------------------------------
lat = [r["latency_ms"] for r in rows]
jit = [r["jitter_ms"] for r in rows]
mean_lat, stdev_lat = statistics.mean(lat), statistics.stdev(lat)
mean_jit, stdev_jit = statistics.mean(jit), statistics.stdev(jit)

print(f"[collect_metrics] {len(rows)} samples → {out_csv}")
print(f"Latency (ms): mean={mean_lat:.2f}, stdev={stdev_lat:.2f}")
print(f"Jitter  (ms): mean={mean_jit:.2f}, stdev={stdev_jit:.2f}")

# ------------------------------------------------------------
# 7. Compute Update Rate (Cycles per Second) per Client
# ------------------------------------------------------------
df = pd.DataFrame(rows)
rates = []
for cid, group in df.groupby("client_id"):
    tmin = group["server_timestamp_ms"].min()
    tmax = group["server_timestamp_ms"].max()
    if tmax > tmin:
        rate = len(group) / ((tmax - tmin) / 1000.0)
        rates.append((cid, rate))

print("\n=== Average Cycles per Second (Snapshots/sec) per Client ===")
if rates:
    for cid, rps in sorted(rates):
        print(f"Client {cid}: {rps:.2f} cycles/sec")
    avg_rate = sum(r for _, r in rates) / len(rates)
else:
    avg_rate = 0.0

# ------------------------------------------------------------
# 8. Average CPU Usage
# ------------------------------------------------------------
avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
print(f"\nAverage cycles/sec per client: {avg_rate:.2f}")
print(f"Average CPU usage:             {avg_cpu:.2f}%")

# ------------------------------------------------------------
# 9. Save summary file for plotting
# ------------------------------------------------------------
with open("collect_metrics_summary.txt", "w") as fsum:
    fsum.write("=== Performance Summary ===\n")
    fsum.write(f"Samples: {len(rows)}\n")
    fsum.write(f"Latency mean={mean_lat:.2f} stdev={stdev_lat:.2f}\n")
    fsum.write(f"Jitter  mean={mean_jit:.2f} stdev={stdev_jit:.2f}\n\n")
    for cid, rps in sorted(rates):
        fsum.write(f"Client {cid}: {rps:.2f} cycles/sec\n")
    fsum.write(f"\nAverage cycles/sec per client: {avg_rate:.2f}\n")
    fsum.write(f"Average CPU usage: {avg_cpu:.2f}%\n")

# ------------------------------------------------------------
# 10. Performance Goal Summary
# ------------------------------------------------------------
if avg_rate >= 20 and mean_lat <= 50 and avg_cpu < 60:
    print("\n✅ Performance goal met: ≥20 cycles/sec per client, latency ≤50 ms, CPU < 60%")
else:
    print("\n⚠ Performance goal not met.")
    print("   Target: ≥20 cycles/sec/client, latency ≤50 ms, CPU < 60%")