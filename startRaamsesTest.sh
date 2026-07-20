#!/usr/bin/env bash
#
# Raamses Automated Test Launcher
#
# Starts the mock Raamses server, device emulators, and optional live dashboard.
# Supports configurable device types, timeouts, and custom log files.
#
# Usage:
#   ./startRaamsesTest.sh                                      # defaults: 3 emulators, no timeout
#   ./startRaamsesTest.sh --devicetype=cyd                     # single device
#   ./startRaamsesTest.sh --devicetype=cyd --devicetype=watch  # multiple devices
#   ./startRaamsesTest.sh --devicetype=DesktopFull             # full desktop dashboard
#   ./startRaamsesTest.sh -t 60s --log ./test.log              # timeout + custom log
#
# Arguments:
#   --devicetype=<type>   Device emulator type(s). Repeat for multiple.
#                         Supported: cyd, epaper, watch, DesktopFull
#   -t, --timeout=<dur>   Run duration then auto-shutdown. Format: 20s, 5m, 2h, or no limit.
#   --log=<path>          Log output file (default: /tmp/raamses_test_<date>.log)
#   --monitor             Launch the live htop-style dashboard (implies DesktopFull)
#   --no-log              Suppress log display after launch
#   -h, --help            Show this help text
#
# Examples:
#   ./startRaamsesTest.sh --devicetype=DesktopFull -t 20s --log ./testlog.log
#   ./startRaamsesTest.sh --devicetype=cyd --devicetype=watch --monitor
#   ./startRaamsesTest.sh --devicetype=epaper -t 5m

set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
SERVER_PY="${SCRIPT_DIR}/src/linux/rgs/server/mock_server.py"
EMULATOR_PY="${SCRIPT_DIR}/src/linux/rgs/client/device_emulator.py"
MONITOR_PY="${SCRIPT_DIR}/src/linux/rgs/monitor.py"
PORT=9999
TIMEOUT=""
LOG_FILE="/tmp/raamses_test_$(date +%Y%m%d_%H%M%S).log"
MONITOR=false
NO_LOG=false
SHOW_LOG=true
DEVICE_TYPES=()
PIDS=()

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ─── Helpers ─────────────────────────────────────────────────────────────────
print_header() {
    local w=60
    local title="$1"
    echo ""
    echo -e "${CYAN}$(printf '═%.0s' $(seq 1 $w))${NC}"
    echo -e "${CYAN}║${NC} $(printf '%*s' $(( (w-${#title}-2)/2 )) "")${BOLD}${title}${NC}$(printf '%*s' $(( (w-${#title}-2)/2 + (w-${#title})%2 -1 )) "") ${CYAN}║${NC}"
    echo -e "${CYAN}$(printf '═%.0s' $(seq 1 $w))${NC}"
}

print_status() {
    local msg="$1"
    local icon="${2:-●}"
    local color="${3:-$GREEN}"
    printf "  ${color}${icon}${NC} %s\n" "$msg"
}

print_info() {
    local msg="$1"
    printf "  ${CYAN}>${NC} %s\n" "$msg"
}

print_warning() {
    printf "  ${YELLOW}⚠${NC} %s\n" "$1"
}

# ─── Argument Parsing ───────────────────────────────────────────────────────
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --devicetype=*)
                DEVICE_TYPES+=("${1#*=}")
                shift
                ;;
            -t)
                # Accept: -t 20s (with space)
                if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                    TIMEOUT="$2"
                    shift 2
                else
                    echo -e "${RED}Error: --timeout requires a value (e.g. 20s, 5m, 2h)${NC}"
                    exit 1
                fi
                ;;
            --timeout=*)
                TIMEOUT="${1#*=}"
                shift
                ;;
            --log)
                # Accept: --log path (with space)
                if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                    LOG_FILE="$2"
                    shift 2
                else
                    echo -e "${RED}Error: --log requires a file path${NC}"
                    exit 1
                fi
                ;;
            --log=*)
                LOG_FILE="${1#*=}"
                shift
                ;;
            --monitor)
                MONITOR=true
                shift
                ;;
            --no-log)
                NO_LOG=true
                SHOW_LOG=false
                shift
                ;;
            -h|--help)
                head -38 "$0" | tail -24
                exit 0
                ;;
            *)
                echo -e "${RED}Error: Unknown option: $1${NC}"
                echo "Run with --help for usage."
                exit 1
                ;;
        esac
    done
}

# ─── Cleanup ─────────────────────────────────────────────────────────────────
CLEANUP_DONE=false

cleanup() {
    if [[ "$CLEANUP_DONE" == true ]]; then
        return
    fi
    CLEANUP_DONE=true
    
    echo ""
    echo -e "${YELLOW}[Cleanup] Shutting down Raamses services...${NC}"
    # Kill all managed processes
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    # Kill any leftover python processes on port 9999
    local port_pids
    port_pids=$(ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K\d+' | tr '\n' ' ' || true)
    if [[ -n "$port_pids" ]]; then
        kill $port_pids 2>/dev/null || true
    fi
    # Kill any background monitor or tail jobs
    local mon_pid
    mon_pid=$(jobs -p 2>/dev/null | tr ' ' '\n' || true)
    if [[ -n "$mon_pid" ]]; then
        echo "$mon_pid" | while read -r jpid; do
            [[ -n "$jpid" ]] && kill "$jpid" 2>/dev/null || true
        done
    fi
    echo -e "${GREEN}[Cleanup] All processes stopped.${NC}"
}

trap cleanup EXIT

# ─── Validation ──────────────────────────────────────────────────────────────
validate() {
    # Check required files
    if [[ ! -f "$SERVER_PY" ]]; then
        echo -e "${RED}Error: Mock server not found: $SERVER_PY${NC}"
        exit 1
    fi
    if [[ ! -f "$EMULATOR_PY" ]]; then
        echo -e "${RED}Error: Device emulator not found: $EMULATOR_PY${NC}"
        exit 1
    fi

    # If no device types specified, use defaults
    if [[ ${#DEVICE_TYPES[@]} -eq 0 ]]; then
        DEVICE_TYPES=("cyd" "epaper" "watch")
        print_info "No device types specified — using defaults: cyd, epaper, watch"
    fi

    # If DesktopFull or --monitor, launch the monitor
    if [[ "$MONITOR" == true ]]; then
        # DesktopFull is synonymous with --monitor flag
        true
    fi

    # Validate timeout format (simple check)
    if [[ -n "$TIMEOUT" ]]; then
        if [[ ! "$TIMEOUT" =~ ^[0-9]+[smh]$ ]]; then
            print_warning "Timeout format should be like 20s, 5m, or 2h. Got: $TIMEOUT"
        fi
    fi
}

# ─── Startup ─────────────────────────────────────────────────────────────────
start_server() {
    print_status "Starting mock Raamses server..." "▶" "$CYAN"
    print_info "Port: $PORT | Log: $LOG_FILE"

    > "$LOG_FILE"  # Clear/create log

    python3 -u "$SERVER_PY" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    PIDS+=($pid)
    print_status "Server PID: $pid" "✓" "$GREEN"

    # Wait for server to bind
    sleep 2
    if ss -tlnp "sport = :$PORT" | grep -q "LISTEN"; then
        print_status "Server listening on port $PORT" "✓" "$GREEN"
    else
        print_warning "Server may not have started — check $LOG_FILE"
        print_info "Contents so far:"
        tail -5 "$LOG_FILE"
    fi
}

start_emulators() {
    for devtype in "${DEVICE_TYPES[@]}"; do
        case "$devtype" in
            DesktopFull)
                # Skip — handled by monitor below
                ;;
            cyd|epaper|watch|legacy)
                local device_id="emu-${devtype}-$(date +%s)"
                print_status "Starting ${devtype} emulator..." "▶" "$CYAN"
                python3 -u "$EMULATOR_PY" \
                    --device-type="$devtype" \
                    --device-id="$device_id" \
                    --host 127.0.0.1 \
                    --port "$PORT" \
                    >> "$LOG_FILE" 2>&1 &
                local pid=$!
                PIDS+=($pid)
                print_status "${devtype} running (id=${device_id})" "✓" "$GREEN"
                ;;
            *)
                print_warning "Unknown device type: $devtype (skipping)"
                print_info "Supported: cyd, epaper, watch, legacy, DesktopFull"
                ;;
        esac
    done
}

start_monitor() {
    if [[ "$MONITOR" == true ]] || [[ " ${DEVICE_TYPES[*]} " =~ " DesktopFull " ]]; then
        if [[ -f "$MONITOR_PY" ]]; then
            print_status "Starting live dashboard..." "▶" "$CYAN"
            $VENV_PYTHON "$MONITOR_PY" >> "$LOG_FILE" 2>&1 &
            local pid=$!
            PIDS+=($pid)
            print_status "Dashboard running" "✓" "$GREEN"
            print_info "Dashboard reads from: $LOG_FILE"
        else
            print_warning "Monitor not found at $MONITOR_PY"
        fi
    fi
}

# ─── Timeout Handler ─────────────────────────────────────────────────────────
handle_timeout() {
    if [[ -n "$TIMEOUT" ]]; then
        print_status "Timeout of $TIMEOUT reached — shutting down..." "⏱" "$YELLOW"
        cleanup
        echo ""
        echo -e "${BOLD}Test complete. Log file: $LOG_FILE${NC}"
        echo ""
        exit 0
    fi
}

start_timeout_timer() {
    if [[ -n "$TIMEOUT" ]]; then
        # Parse timeout to seconds
        local seconds
        case "${TIMEOUT: -1}" in
            s) seconds="${TIMEOUT%s}" ;;
            m) seconds=$(( ${TIMEOUT%m} * 60 )) ;;
            h) seconds=$(( ${TIMEOUT%h} * 3600 )) ;;
            *) seconds=0 ;;
        esac
        if [[ $seconds -gt 0 ]]; then
            print_status "Auto-shutdown in $TIMEOUT ($seconds seconds)" "⏱" "$YELLOW"
            (sleep "$seconds" && handle_timeout) &
        fi
    fi
}

# ─── Display ─────────────────────────────────────────────────────────────────
display_live_log() {
    if [[ "$SHOW_LOG" == true && "$NO_LOG" == false ]]; then
        print_status "Following log output (Ctrl+C to stop)..." "▶" "$CYAN"
        print_info "Log file: $LOG_FILE"
        print_info "Commands: tail -f $LOG_FILE  | grep ALERT | grep CRITICAL"
        echo ""

        # Show initial log
        if [[ -s "$LOG_FILE" ]]; then
            print_info "Recent log entries:"
            tail -20 "$LOG_FILE"
            echo ""
        fi

        # Follow the log
        tail -f "$LOG_FILE" &
        local tail_pid=$!
        wait $tail_pid
    else
        echo ""
        echo -e "${BOLD}Test complete. Log file: $LOG_FILE${NC}"
        echo ""
    fi
}

# ─── Quick Stats ─────────────────────────────────────────────────────────────
show_stats() {
    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  RAAMSES TEST STATUS${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Server
    if ss -tlnp "sport = :$PORT" | grep -q "LISTEN"; then
        print_status "Server" "●" "$GREEN" "port $PORT"
    else
        print_status "Server" "●" "$RED" "NOT RUNNING"
    fi

    # Emulators
    local emu_count=0
    local emu_pids
    emu_pids=$(ps aux | grep "device_emulator.py" | grep -v grep | wc -l || true)
    if [[ $emu_pids -gt 0 ]]; then
        print_status "Emulators" "●" "$GREEN" "$emu_pids running"
    else
        print_status "Emulators" "○" "$YELLOW" "none"
    fi

    # Log file
    if [[ -f "$LOG_FILE" ]]; then
        local lines alerts commands
        lines=$(wc -l < "$LOG_FILE" 2>/dev/null)
        lines=$(echo "$lines" | tr -d '[:space:]')
        
        alerts=$(grep -c "\[ALERT\]" "$LOG_FILE" 2>/dev/null) || alerts=0
        alerts=$(echo "$alerts" | tr -d '[:space:]')
        
        commands=$(grep -c "\[COMMAND\]" "$LOG_FILE" 2>/dev/null) || commands=0
        commands=$(echo "$commands" | tr -d '[:space:]')
        
        echo ""
        echo -e "  ${CYAN}Log:${NC} $LOG_FILE"
        echo -e "  ${CYAN}Lines:${NC} ${lines} | ${CYAN}Alerts:${NC} ${alerts} | ${CYAN}Commands:${NC} ${commands}"
    fi

    # Device types
    if [[ ${#DEVICE_TYPES[@]} -gt 0 ]]; then
        echo ""
        printf "  ${CYAN}Devices:${NC} "
        local first=true
        for dt in "${DEVICE_TYPES[@]}"; do
            if [[ "$first" == true ]]; then first=false; else printf ", "; fi
            if [[ "$dt" == "DesktopFull" ]]; then
                printf "DesktopFull(monitor)"
            else
                printf "${dt}"
            fi
        done
        echo ""
    fi

    echo ""
    echo -e "${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
    parse_args "$@"

    print_header "RAAMSES TEST LAUNCHER"

    echo ""
    print_info "Device types: ${DEVICE_TYPES[*]}"
    if [[ -n "$TIMEOUT" ]]; then
        print_info "Timeout: $TIMEOUT"
    fi
    print_info "Log file: $LOG_FILE"
    if [[ "$MONITOR" == true ]]; then
        print_info "Monitor: enabled"
    fi

    validate

    echo ""
    echo -e "${BOLD}Starting services...${NC}"
    echo ""

    start_server
    start_emulators
    start_monitor
    start_timeout_timer

    show_stats

    display_live_log
}

main "$@"
