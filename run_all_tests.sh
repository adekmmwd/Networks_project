#!/bin/bash
# ============================================================
# run_all_tests.sh — Project 2: Multiplayer Game State Synchronization
# Runs ALL 4 required scenarios (baseline + loss 2% + loss 5% + delay 100ms)
#   → 5 repetitions each (as required: "repeat each measurement at least 5 times")
#   → Captures .pcap for the first 2 runs of each scenario (requirement)
#   → Saves everything in ./results/<scenario>/run1..run5/
#   → Automatically collects per-run metrics.csv using your existing collect_metrics.py
#   → At the end generates summary plots for the report (one script call)
# ============================================================

set -e

# ---------------------- CONFIGURATION ----------------------
INTERFACE=${INTERFACE:-lo}          # Use "lo" for local testing, change to eth0/wlan0 if needed
NUM_RUNS=5                          # 5 repetitions per scenario
RUN_DURATION=1                    # 120s game + 10s safety margin
SERVER_PORT=${SERVER_PORT:-5000}    # ← CHANGE IF YOUR server.py USES ANOTHER PORT
RESULTS_DIR="results"

# Clean previous results (comment if you want to keep them)
rm -rf ${RESULTS_DIR}
mkdir -p ${RESULTS_DIR}

# ---------------------- SCENARIOS ----------------------
declare -A SCENARIOS
SCENARIOS["baseline"]="None"
SCENARIOS["loss_2_lan"]="loss 2%"
SCENARIOS["loss_5_wan"]="loss 5%"
SCENARIOS["delay_100ms"]="delay 100ms"

# ---------------------- HELPER FUNCTIONS ----------------------
cleanup_netem() {
    echo "[INFO] Cleaning netem on ${INTERFACE}"
    sudo tc qdisc del dev ${INTERFACE} root 2>/dev/null || true
}

apply_netem() {
    local config="$1"
    if [ "$config" = "None" ]; then
        return
    fi
    echo "[INFO] Applying: sudo tc qdisc add dev ${INTERFACE} root netem ${config}"
    cleanup_netem
    sudo tc qdisc add dev ${INTERFACE} root netem ${config}
}

start_capture() {
    local pcap_file="$1"
    echo "[INFO] Starting packet capture → ${pcap_file}"
    sudo tcpdump -i ${INTERFACE} udp port ${SERVER_PORT} -w "${pcap_file}" &
    TCPDUMP_PID=$!
}

stop_capture() {
    if [ ! -z "${TCPDUMP_PID}" ]; then
        echo "[INFO] Stopping packet capture..."
        sudo kill ${TCPDUMP_PID} 2>/dev/null || true
        wait ${TCPDUMP_PID} 2>/dev/null || true
        TCPDUMP_PID=""
    fi
}

# ---------------------- MAIN LOOP ----------------------
for scenario in "${!SCENARIOS[@]}"; do
    config="${SCENARIOS[$scenario]}"
    echo "=========================================================="
    echo "STARTING SCENARIO: ${scenario} (${config})"
    echo "=========================================================="

    mkdir -p "${RESULTS_DIR}/${scenario}"

    for run in $(seq 1 ${NUM_RUNS}); do
        RUN_DIR="${RESULTS_DIR}/${scenario}/run${run}"
        mkdir -p "${RUN_DIR}"

        SERVER_LOG="${RUN_DIR}/server_log.txt"
        CLIENT_LOG_PREFIX="${RUN_DIR}/client"
        METRICS_CSV="${RUN_DIR}/metrics.csv"
        PCAP_FILE="${RUN_DIR}/capture.pcap"

        echo "--------------------------------------------------"
        echo "Scenario: ${scenario} | Run: ${run}/${NUM_RUNS}"
        echo "--------------------------------------------------"

        # 1. Set network condition
        if [ "$config" = "None" ]; then
            cleanup_netem
        else
            apply_netem "$config"
        fi

        # 2. Start packet capture for first 2 runs only
        if [ ${run} -le 2 ]; then
            start_capture "${PCAP_FILE}"
        fi

        # 3. Start server
        echo "[INFO] Launching server..."
        python3 server.py > "${SERVER_LOG}" 2>&1 &
        SERVER_PID=$!
        sleep 3

        # 4. Start 4 clients (staggered as in your original script)
        echo "[INFO] Launching 4 clients..."
        for i in {1..4}; do
            python3 client.py --id ${i} > "${CLIENT_LOG_PREFIX}${i}_log.txt" 2>&1 &
            sleep 0.8
        done

        # 5. Run the test
        echo "[INFO] Running for ${RUN_DURATION}s..."
        sleep ${RUN_DURATION}

        # 6. Stop everything
        echo "[INFO] Stopping server and clients..."
        kill ${SERVER_PID} 2>/dev/null || true
        pkill -f "client.py" 2>/dev/null || true
        stop_capture
        wait 2>/dev/null || true

        # 7. Clean netem
        cleanup_netem

        # 8. Collect metrics for this run
        echo "[INFO] Collecting metrics for this run..."
        python3 collect_metrics.py "${SERVER_LOG}" "${CLIENT_LOG_PREFIX}"*_log.txt
        mv metrics.csv "${METRICS_CSV}" 2>/dev/null || true   # in case your script names it differently

        echo "[DONE] Run ${run} finished → ${RUN_DIR}"
        echo
    done

    echo "=========================================================="
    echo "SCENARIO ${scenario} COMPLETED (5 runs + pcaps for run1 & run2)"
    echo "=========================================================="
    echo
done

# ---------------------- FINAL SUMMARY PLOTS ----------------------
echo "All scenarios finished!"
echo "Generating summary plots (latency, jitter, position error, bandwidth vs scenario)..."

# This assumes you will create (or already have) a summarize_and_plot.py that:
# - walks through results/*/*/metrics.csv
# - computes mean/median/95th for each scenario
# - produces the required report plots
# You only need to implement it once — example skeleton below

python3 summarize_and_plot.py ${RESULTS_DIR}

echo "=========================================================="
echo "ALL TESTS COMPLETED!"
echo "Results: ./${RESULTS_DIR}/"
echo "Include the two .pcap files per scenario in your submission."
echo "Use the generated summary plots in your report."
echo "=========================================================="