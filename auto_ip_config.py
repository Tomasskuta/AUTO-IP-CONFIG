import subprocess
import ctypes
import time
import datetime
import re

# --- CONFIGURATION SECTION ---
INTERFACE_NAME = "Wi-Fi"
CHECK_INTERVAL = 30  # Seconds between checks

KNOWN_NETWORKS = {
    "ABB PS PCU": {
        "mode": "static",
        "ip": "172.17.4.199",
        "subnet": "255.255.252.0",
        "gateway": "172.17.4.31",
        "dns": "0.0.0.0"
    },
    "ABB SB PCU": {
        "mode": "static",
        "ip": "172.17.4.199",
        "subnet": "255.255.252.0",
        "gateway": "172.17.4.31",
        "dns": "0.0.0.0"
    }
}


# -----------------------------

def log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def get_netsh_output(command):
    """Runs a netsh command and returns the output string hidden."""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return subprocess.check_output(command, encoding="utf-8", errors="ignore", startupinfo=si)
    except Exception:
        return ""


def get_connected_ssid():
    """Gets current SSID."""
    output = get_netsh_output(["netsh", "wlan", "show", "interfaces"])
    for line in output.split('\n'):
        if "SSID" in line and "BSSID" not in line:
            parts = line.split(":")
            if len(parts) > 1:
                return parts[1].strip()
    return None


def get_current_details():
    """Parses netsh to find if we are currently DHCP or Static, and what the IP is."""
    output = get_netsh_output(["netsh", "interface", "ip", "show", "config", INTERFACE_NAME])

    details = {
        "dhcp_enabled": False,
        "ip": None
    }

    # Regex to find 'DHCP enabled: Yes/No' and 'IP Address: x.x.x.x'
    # Note: Output format varies slightly by Windows version/language.
    # This assumes English Windows.
    if re.search(r"DHCP enabled:\s+Yes", output, re.IGNORECASE):
        details["dhcp_enabled"] = True

    ip_match = re.search(r"IP Address:\s+([0-9.]+)", output)
    if ip_match:
        details["ip"] = ip_match.group(1)

    return details


def set_static_ip(config):
    log(f"Enforcing Static IP: {config['ip']}...")
    try:
        # Set IP
        subprocess.run(
            f'netsh interface ip set address "{INTERFACE_NAME}" static {config["ip"]} {config["subnet"]} {config["gateway"]}',
            shell=True, check=True)
        # Set DNS
        subprocess.run(f'netsh interface ip set dns "{INTERFACE_NAME}" static {config["dns"]}', shell=True, check=True)
        log("✅ Settings enforced.")
    except:
        log("❌ Failed to apply Static IP.")


def set_dhcp():
    log("Enforcing DHCP (Auto)...")
    try:
        subprocess.run(f'netsh interface ip set address "{INTERFACE_NAME}" dhcp', shell=True, check=True)
        subprocess.run(f'netsh interface ip set dns "{INTERFACE_NAME}" dhcp', shell=True, check=True)
        log("✅ DHCP enforced.")
    except:
        log("❌ Failed to apply DHCP.")


def main():
    if not is_admin():
        print("⚠️  Script must be run as Administrator (SYSTEM or Admin User).")
        time.sleep(5)
        return

    log(f"--- Enforcer Running on {INTERFACE_NAME} ---")

    while True:
        current_ssid = get_connected_ssid()
        current_config = get_current_details()  # Get actual current IP state

        if current_ssid:
            # 1. Determine what the settings SHOULD be
            target_settings = KNOWN_NETWORKS.get(current_ssid)

            if target_settings:
                # Target is KNOWN. Check if matches spec.
                desired_mode = target_settings.get("mode", "dhcp")

                if desired_mode == "dhcp":
                    # We want DHCP. Are we on DHCP?
                    if not current_config["dhcp_enabled"]:
                        log(f"VIOLATION: '{current_ssid}' requires DHCP, but Static detected.")
                        set_dhcp()

                elif desired_mode == "static":
                    # We want Static. Are we Static AND is the IP correct?
                    desired_ip = target_settings["ip"]

                    if current_config["dhcp_enabled"]:
                        log(f"VIOLATION: '{current_ssid}' requires Static, but DHCP detected.")
                        set_static_ip(target_settings)
                    elif current_config["ip"] != desired_ip:
                        log(f"VIOLATION: IP is {current_config['ip']}, expected {desired_ip}.")
                        set_static_ip(target_settings)

                    # If DHCP is False and IP matches, do nothing (Healthy)

            else:
                # Target is UNKNOWN -> Default to DHCP
                if not current_config["dhcp_enabled"]:
                    log("Unknown network detected. Enforcing DHCP safety net.")
                    set_dhcp()

        else:
            # Not connected. Usually do nothing, or force DHCP to be ready for next connection
            pass

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()