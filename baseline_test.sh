#!/bin/bash
# ============================================================
#  Baseline Local Test Script — Phase 1
#  Project 2: Multiplayer Game State Synchronization (VAP-1)
# ============================================================

set -e

SERVER_LOG="server_log.txt"
CLIENT_LOG_PREFIX="client"
METRICS_CSV="metrics.csv"
RUN_DURATION=120   # seconds

echo "=== Starting Phase-1 Baseline Local Test ==="
rm -f ${SERVER_LOG} ${CLIENT_LOG_PREFIX}_*.txt ${METRICS_CSV} *.png

# ------------------------------------------------------------
# Step 1 – Launch server
# ------------------------------------------------------------
echo "[INFO] Launching server..."
python3 server.py > ${SERVER_LOG} 2>&1 &
SERVER_PID=$!
sleep 2

# ------------------------------------------------------------
# Step 2 – Launch 4 clients
# ------------------------------------------------------------
for i in 1 2 3 4; do
  LOGFILE="${CLIENT_LOG_PREFIX}${i}_log.txt"
  echo "[INFO] Launching client ${i}..."
  python3 client.py --id ${i} > ${LOGFILE} 2>&1 &
  sleep 0.8
done

# ------------------------------------------------------------
# Step 3 – Run test
# ------------------------------------------------------------
echo "[INFO] Running for ${RUN_DURATION}s..."
sleep ${RUN_DURATION}

# ------------------------------------------------------------
# Step 4 – Stop server & clients
# ------------------------------------------------------------
echo "[INFO] Stopping server (PID=${SERVER_PID})..."
kill ${SERVER_PID} 2>/dev/null || true
pkill -f "client.py" 2>/dev/null || true
sleep 1

# ------------------------------------------------------------
# Step 5 – Collect metrics & generate plots
# ------------------------------------------------------------
echo "[INFO] Collecting metrics..."
python3 collect_metrics.py ${SERVER_LOG} ${CLIENT_LOG_PREFIX}*.txt

echo "[INFO] Generating plots..."
python3 plot_metrics.py ${METRICS_CSV}

# ------------------------------------------------------------
# Step 6 – Summary
# ------------------------------------------------------------
echo "=== Baseline Test Complete ==="
echo
tail -n 15 ${SERVER_LOG} || true
echo
echo "[INFO] Metrics saved to ${METRICS_CSV}"
echo "[INFO] Plots: latency_timeseries.png and jitter_hist.png"
echo "==========================================================="