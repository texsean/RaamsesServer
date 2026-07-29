#!/usr/bin/env python3
"""Sim script — triggers an "Agent needs help" alert on the gateway.

This simulates an agent being in trouble. Once triggered, any heartbeat
response from the gateway will include "alert": "Agent needs help" in the
JSON response. WiFi-connected Meshtastic devices will see this in their
heartbeat response and can display the alert.

Usage:
    # Trigger alert for a specific device
    python3 sim_alert.py --trigger --device-id cyd-001

    # Trigger alert (auto-registers a fake agent first, then alerts it)
    python3 sim_alert.py --trigger

    # Clear the alert
    python3 sim_alert.py --clear --device-id cyd-001

    # Check current alert state
    python3 sim_alert.py --check --device-id cyd-001

    # List all agents and their alert states
    python3 sim_alert.py --list

    # Continuous mode: trigger alert, wait, clear, wait, repeat
    # (useful for testing ALERT/CLEAR cycles on a display device)
    python3 sim_alert.py --cycle --device-id cyd-001 --interval 30
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def gateway_url(host, port, path):
    return f"http://{host}:{port}{path}"


def post_json(host, port, path, data):
    """POST JSON to the gateway and return the response."""
    url = gateway_url(host, port, path)
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode()}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def get_json(host, port, path):
    """GET JSON from the gateway."""
    url = gateway_url(host, port, path)
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def trigger_alert(host, port, device_id):
    """Trigger an alert on a device."""
    # First register the device (in case it's not registered yet)
    reg = post_json(host, port, "/register", {
        "device_id": device_id,
        "device_type": "cyd",
    })
    print(f"Register: {reg.get('status', reg.get('error', '?'))}")

    # Send update with alert
    resp = post_json(host, port, "/update", {
        "device_id": device_id,
        "alert": "Agent needs help",
    })
    print(f"Alert triggered: {resp.get('status', resp.get('error', '?'))}")
    return resp


def clear_alert(host, port, device_id):
    """Clear an alert on a device."""
    resp = post_json(host, port, "/update", {
        "device_id": device_id,
        "alert_clear": "resolved",
    })
    print(f"Alert cleared: {resp.get('status', resp.get('error', '?'))}")
    return resp


def check_alert(host, port, device_id):
    """Check alert state for a device."""
    agents = get_json(host, port, "/agents")
    if "error" in agents:
        print(f"Error: {agents['error']}")
        return None
    for a in agents.get("agents", []):
        if a["device_id"] == device_id:
            print(f"Device: {a['device_id']}")
            print(f"  Transport:    {a.get('transport', '?')}")
            print(f"  Alert active: {a.get('alert_active', False)}")
            print(f"  Alert seq:    {a.get('alert_seq', None)}")
            print(f"  Last HB:      {a.get('last_heartbeat', 'never')}")
            return a
    print(f"Device {device_id} not found")
    return None


def list_agents(host, port):
    """List all agents and their alert states."""
    agents = get_json(host, port, "/agents")
    if "error" in agents:
        print(f"Error: {agents['error']}")
        return
    print(f"Agents ({agents.get('count', 0)}):")
    for a in agents.get("agents", []):
        alert = "ALERT" if a.get("alert_active") else "ok"
        transport = a.get("transport", "?")
        print(f"  [{alert:5s}] {a['device_id']:20s} transport={transport}")


def cycle_mode(host, port, device_id, interval):
    """Continuously trigger and clear alerts on a cycle."""
    print(f"Cycle mode: trigger/clear every {interval}s for device {device_id}")
    print("Press Ctrl+C to stop")
    print()

    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"--- Cycle {cycle} ---")

            # Trigger alert
            print(f"  Triggering alert...")
            trigger_alert(host, port, device_id)
            time.sleep(interval)

            # Clear alert
            print(f"  Clearing alert...")
            clear_alert(host, port, device_id)
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Sim script — trigger/clear 'Agent needs help' alerts"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Gateway host")
    parser.add_argument("--port", type=int, default=8765, help="Gateway port")
    parser.add_argument("--device-id", default="sim-agent-001",
                       help="Device ID to alert (default: sim-agent-001)")
    parser.add_argument("--trigger", action="store_true",
                       help="Trigger 'Agent needs help' alert")
    parser.add_argument("--clear", action="store_true",
                       help="Clear the alert")
    parser.add_argument("--check", action="store_true",
                       help="Check alert state for device")
    parser.add_argument("--list", action="store_true",
                       help="List all agents and alert states")
    parser.add_argument("--cycle", action="store_true",
                       help="Continuous trigger/clear cycle mode")
    parser.add_argument("--interval", type=int, default=30,
                       help="Cycle interval in seconds (default: 30)")
    args = parser.parse_args()

    if args.list:
        list_agents(args.host, args.port)
    elif args.check:
        check_alert(args.host, args.port, args.device_id)
    elif args.trigger:
        trigger_alert(args.host, args.port, args.device_id)
    elif args.clear:
        clear_alert(args.host, args.port, args.device_id)
    elif args.cycle:
        cycle_mode(args.host, args.port, args.device_id, args.interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()