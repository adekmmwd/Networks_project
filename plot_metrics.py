#!/usr/bin/env python3
"""
plot_metrics.py — Phase 1 baseline plotting
Usage:
    python3 plot_metrics.py metrics.csv
Outputs:
    latency_timeseries.png
    jitter_hist.png
"""

import sys, csv, matplotlib.pyplot as plt

if len(sys.argv) < 2:
    print("Usage: python3 plot_metrics.py metrics.csv")
    sys.exit(1)

csv_file = sys.argv[1]
lat, jit = [], []

with open(csv_file) as f:
    r = csv.DictReader(f)
    for row in r:
        lat.append(float(row["latency_ms"]))
        jit.append(float(row["jitter_ms"]))

if not lat:
    print("[plot_metrics] No data to plot.")
    sys.exit(0)

# Latency time-series
plt.figure(figsize=(8,4))
plt.plot(lat, marker='.', linestyle='-', alpha=0.7)
plt.title("Snapshot Latency (ms)")
plt.xlabel("Sample Index")
plt.ylabel("Latency (ms)")
plt.grid(True)
plt.tight_layout()
plt.savefig("latency_timeseries.png")
print("[plot_metrics] Saved latency_timeseries.png")

# Jitter histogram
plt.figure(figsize=(6,4))
plt.hist(jit, bins=40, alpha=0.8)
plt.title("Jitter Distribution (ms)")
plt.xlabel("Jitter (ms)")
plt.ylabel("Count")
plt.tight_layout()
plt.savefig("jitter_hist.png")
print("[plot_metrics] Saved jitter_hist.png")