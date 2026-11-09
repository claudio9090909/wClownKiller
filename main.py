
import os, sys, json, time, random, string
import subprocess, datetime, signal, math
from pathlib import Path

# ─── Auto-install ─────────────────────────────────────────────────────────────
def _ensure_deps():
    try:
        import rich, requests
    except ImportError:
        print("[*] Instalando dependências...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "requests", "-q"],
            check=True
        )
        os.execv(sys.executable, [sys.executable] + sys.argv)

_ensure_deps()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.theme import Theme
from rich import box
import requests as _requests

# ─── Tema ─────────────────────────────────────────────────────────────────────
THEME = Theme({
    "primary":  "bold red",
    "secondary":"red",
    "accent":   "bright_red",
    "muted":    "dim white",
    "good":     "bold green",
    "warn":     "bold yellow",
    "danger":   "bold red",
    "info":     "bold cyan",
})

console  = Console(theme=THEME, highlight=False)
RDIR     = Path("/sdcard/WiFiMaster_Reports")

# ─── Banner ───────────────────────────────────────────────────────────────────
BANNER = r"""
 ██╗    ██╗██╗███████╗██╗    ███╗   ███╗ █████╗ ███████╗████████╗███████╗██████╗
 ██║    ██║██║██╔════╝██║    ████╗ ████║██╔══██╗██╔════╝╚══██╔══╝██╔════╝██╔══██╗
 ██║ █╗ ██║██║█████╗  ██║    ██╔████╔██║███████║███████╗   ██║   █████╗  ██████╔╝
 ██║███╗██║██║██╔══╝  ██║    ██║╚██╔╝██║██╔══██║╚════██║   ██║   ██╔══╝  ██╔══██╗
 ╚███╔███╔╝██║██║     ╚═╝    ██║ ╚═╝ ██║██║  ██║███████║   ██║   ███████╗██║  ██║
  ╚══╝╚══╝ ╚═╝╚═╝            ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
"""

# ─── Helpers ──────────────────────────────────────────────────────────────────
def clear():
    os.system("clear")

def run_cmd(cmd: str, timeout: int = 15) -> tuple:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)

def signal_bars(rssi: int) -> str:
    if rssi >= -50: return "[good]▂▄▆█[/good]"
    if rssi >= -65: return "[good]▂▄▆[/good][muted]█[/muted]"
    if rssi >= -75: return "[warn]▂▄[/warn][muted]▆█[/muted]"
    return "[danger]▂[/danger][muted]▄▆█[/muted]"

def rssi_quality(rssi: int) -> int:
    if rssi >= -50:  return 100
    if rssi <= -100: return 0
    return int(2 * (rssi + 100))

def parse_security(caps: str) -> tuple:
    c = caps.upper()
    if not c or c in ("", "[ESS]", "ESS"):
        return "OPEN", "danger"
    if "WEP"      in c: return "WEP",      "danger"
    if "WPA3"     in c: return "WPA3",     "good"
    if "WPA2-EAP" in c: return "WPA2-EAP", "good"
    if "RSN-EAP"  in c: return "WPA2-EAP", "good"
    if "WPA2"     in c:
        if "TKIP" in c and "CCMP" not in c:
            return "WPA2-TKIP", "warn"
        return "WPA2", "info"
    if "RSN"      in c: return "WPA2",     "info"
    if "WPA"      in c: return "WPA",      "warn"
    return "UNKNOWN", "muted"

def freq_to_channel(freq: int) -> str:
    if freq == 2484: return "14"
    if 2412 <= freq <= 2472: return str((freq - 2412) // 5 + 1)
    if 5170 <= freq <= 5825: return str((freq - 5170) // 5 + 34)
    if 5955 <= freq <= 7115: return str((freq - 5955) // 5 + 1) + " (6G)"
    return str(freq) if freq else "?"

def header():
    clear()
    console.print(Text(BANNER, style="bold red"), justify="center")
    console.print(
        Panel("[secondary]Advanced Wi-Fi Management & Audit Panel[/secondary]",
              border_style="red", padding=(0, 6)),
        justify="center"
    )
    console.print()

def press_enter():
    console.print("\n[muted]  ↵ Enter para continuar...[/muted]", end="")
    input()

def wifi_scan() -> list:
    ok, out = run_cmd("termux-wifi-scaninfo", timeout=25)
    if not ok or not out.strip().startswith("["): return []
    try:
        return json.loads(out)
    except Exception:
        return []

# ─── 1. Scanner ───────────────────────────────────────────────────────────────
def module_scanner():
    header()
    console.print(Panel("[primary]  SCANNER WI-FI[/primary]", border_style="red"))
    console.print("[muted]  Varrendo via termux-api...[/muted]\n")

    networks = []
    with Progress(SpinnerColumn(style="red"),
                  TextColumn("[secondary]{task.description}[/secondary]"),
                  TimeElapsedColumn(), console=console, transient=True) as p:
        t = p.add_task("Scanning...", total=None)
        networks = wifi_scan()
        p.update(t, description=f"Encontradas {len(networks)} redes")
        time.sleep(0.4)

    if not networks:
        console.print("[danger]  Nenhuma rede encontrada.[/danger]")
        console.print("[muted]  Verifique: pkg install termux-api[/muted]")
        press_enter(); return

    networks.sort(key=lambda x: x.get("rssi", -100), reverse=True)

    tbl = Table(
        title=f"[primary]Redes detectadas — {datetime.datetime.now().strftime('%H:%M:%S')}[/primary]",
        border_style="red", header_style="bold red",
        box=box.HEAVY_EDGE, show_lines=True, expand=True,
    )
    tbl.add_column("#",         style="muted",      width=4,  justify="right")
    tbl.add_column("SSID",      style="bold white",  min_width=16)
    tbl.add_column("BSSID",     style="muted",       width=20)
    tbl.add_column("Sinal",     justify="center",    width=12)
    tbl.add_column("dBm",       justify="right",     width=6)
    tbl.add_column("Qualidade", justify="center",    width=10)
    tbl.add_column("Canal",     justify="center",    width=7)
    tbl.add_column("Segurança", justify="center",    min_width=12)

    for i, net in enumerate(networks, 1):
        ssid    = net.get("ssid") or "[dim](oculta)[/dim]"
        bssid   = net.get("bssid", "??:??:??:??:??:??")
        rssi    = net.get("rssi", -100)
        caps    = net.get("capabilities", "")
        sec, ss = parse_security(caps)
        q       = rssi_quality(rssi)
        ch      = freq_to_channel(net.get("frequency", 0))

        tbl.add_row(
            str(i), ssid, bssid,
            signal_bars(rssi), str(rssi),
            f"[{ss}]{q}%[/{ss}]",
            ch,
            f"[{ss}]{sec}[/{ss}]",
        )

    console.print(tbl)
    console.print(f"\n[muted]  Total: {len(networks)} redes[/muted]")
    press_enter()

# ─── 2. Auditoria de Segurança ────────────────────────────────────────────────
def module_audit():
    header()
    console.print(Panel("[primary]  AUDITORIA DE SEGURANÇA[/primary]", border_style="red"))
    console.print("[muted]  Analisando protocolos...[/muted]\n")

    networks = []
    with Progress(SpinnerColumn(style="red"),
                  TextColumn("[secondary]{task.description}[/secondary]"),
                  console=console, transient=True) as p:
        p.add_task("Coletando dados...", total=None)
        networks = wifi_scan()
        time.sleep(0.4)

    if not networks:
        console.print("[danger]  Nenhuma rede detectada.[/danger]")
        press_enter(); return

    tbl = Table(
        title="[primary]Relatório de Auditoria[/primary]",
        border_style="red", header_style="bold red",
        box=box.HEAVY_EDGE, show_lines=True, expand=True,
    )
    tbl.add_column("SSID",       min_width=16)
    tbl.add_column("Protocolo",  justify="center", width=12)
    tbl.add_column("Risco",      justify="center", width=10)
    tbl.add_column("Problemas",  min_width=35)
    tbl.add_column("WPS",        justify="center", width=5)

    risk_count = {"CRÍTICO": 0, "ALTO": 0, "MÉDIO": 0, "BAIXO": 0}

    for net in networks:
        ssid       = net.get("ssid") or "(oculta)"
        caps       = net.get("capabilities", "").upper()
        sec, _     = parse_security(caps)
        wps        = "[warn]✓[/warn]" if "WPS" in caps else "[muted]—[/muted]"
        issues     = []

        if   sec == "OPEN":     risk, rs, rl = 0, "danger", "CRÍTICO"; issues.append("Sem autenticação")
        elif sec == "WEP":      risk, rs, rl = 1, "danger", "CRÍTICO"; issues.append("WEP obsoleto e quebrável")
        elif sec in ("WPA","WPA2-TKIP"): risk, rs, rl = 2, "warn", "ALTO"; issues.append("Cifra TKIP vulnerável")
        elif sec == "WPA2":     risk, rs, rl = 3, "info",   "MÉDIO"
        elif sec in ("WPA2-EAP","WPA3"): risk, rs, rl = 4, "good", "BAIXO"
        else:                   risk, rs, rl = 2, "warn", "MÉDIO"; issues.append("Protocolo não identificado")

        if "WPS" in caps: issues.append("WPS ativo (Pixie Dust)")
        if not net.get("ssid"): issues.append("SSID oculto")

        risk_count[rl] += 1
        issue_str = " · ".join(issues) if issues else "[good]Nenhum crítico[/good]"
        tbl.add_row(ssid, f"[{rs}]{sec}[/{rs}]", f"[{rs}]{rl}[/{rs}]", issue_str, wps)

    console.print(tbl)
    console.print()

    stbl = Table(box=box.SIMPLE, border_style="red", show_header=False, padding=(0,3))
    stbl.add_column(justify="left",  width=12)
    stbl.add_column(justify="center",width=5)
    stbl.add_row("[danger]CRÍTICO[/danger]",  str(risk_count["CRÍTICO"]))
    stbl.add_row("[warn]ALTO[/warn]",          str(risk_count["ALTO"]))
    stbl.add_row("[info]MÉDIO[/info]",          str(risk_count["MÉDIO"]))
    stbl.add_row("[good]BAIXO[/good]",          str(risk_count["BAIXO"]))
    console.print(Panel(stbl, title="[primary]Resumo de Risco[/primary]", border_style="red"))
    press_enter()

# ─── 3. Gerenciador de Senhas ─────────────────────────────────────────────────
def module_passwords():
    header()
    console.print(Panel("[primary]  GERENCIADOR DE SENHAS SALVAS[/primary]", border_style="red"))
    console.print("[muted]  Lê redes salvas do dispositivo. Requer root.[/muted]\n")

    paths = [
        "/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml",
        "/data/misc/wifi/WifiConfigStore.xml",
        "/data/misc/wifi/wpa_supplicant.conf",
    ]

    found_path, content = None, ""
    for p in paths:
        ok, out = run_cmd(f"su -c 'cat {p}'", timeout=10)
        if ok and len(out) > 20:
            found_path, content = p, out
            break

    if not found_path:
        console.print("[danger]  Acesso negado. Root necessário.[/danger]")
        console.print("[muted]  Certifique-se que o Termux tem permissão de root.[/muted]")
        press_enter(); return

    import re
    networks = []

    if "wpa_supplicant" in found_path:
        for block in re.split(r"network=\{", content)[1:]:
            sm = re.search(r'ssid="([^"]+)"', block)
            pm = re.search(r'psk="([^"]+)"', block)
            if sm:
                networks.append({
                    "ssid": sm.group(1),
                    "psk":  pm.group(1) if pm else "[muted]hash[/muted]"
                })
    else:
        ssids = re.findall(r'SSID="([^"]+)"', content)
        psks  = re.findall(r'PreSharedKey="([^"]+)"', content)
        for i, ssid in enumerate(ssids):
            networks.append({
                "ssid": ssid.strip('"'),
                "psk":  psks[i] if i < len(psks) else "[muted]—[/muted]"
            })

    if not networks:
        console.print("[warn]  Nenhuma rede salva encontrada.[/warn]")
        press_enter(); return

    tbl = Table(
        title="[primary]Redes Salvas[/primary]",
        border_style="red", header_style="bold red",
        box=box.HEAVY_EDGE, show_lines=True, expand=True,
    )
    tbl.add_column("#",    width=4, justify="right", style="muted")
    tbl.add_column("SSID", min_width=20, style="bold white")
    tbl.add_column("Senha / PSK", min_width=30, style="secondary")

    for i, net in enumerate(networks, 1):
        tbl.add_row(str(i), net["ssid"], net["psk"])

    console.print(tbl)
    console.print(f"\n[muted]  Fonte: {found_path}[/muted]")
    press_enter()

# ─── 4. Análise de Vulnerabilidades ──────────────────────────────────────────
VULN_MAP = {
    "WEP":    ("Protocolo quebrado via replay/FMS/ChopChop",         "CRÍTICO", "danger"),
    "WPS":    ("WPS ativo — Pixie Dust + brute-force PIN (8 dig)",   "ALTO",    "warn"),
    "OPEN":   ("Rede aberta — tráfego visível, MITM trivial",        "CRÍTICO", "danger"),
    "TKIP":   ("TKIP suscetível a fragmentação e MIC failure",       "ALTO",    "warn"),
    "HIDDEN": ("SSID oculto não impede descoberta via probe request", "BAIXO",   "info"),
    "WPA1":   ("WPA v1 obsoleto — TKIP/MIC attacks",                 "MÉDIO",   "warn"),
}

def module_vulns():
    header()
    console.print(Panel("[primary]  ANÁLISE DE VULNERABILIDADES[/primary]", border_style="red"))
    console.print("[muted]  Mapeamento detalhado de vetores de ataque...[/muted]\n")

    networks = []
    with Progress(SpinnerColumn(style="red"),
                  TextColumn("[secondary]{task.description}[/secondary]"),
                  console=console, transient=True) as p:
        p.add_task("Coletando...", total=None)
        networks = wifi_scan()
        time.sleep(0.4)

    if not networks:
        console.print("[danger]  Nenhuma rede detectada.[/danger]")
        press_enter(); return

    for net in networks:
        ssid  = net.get("ssid") or "(oculta)"
        caps  = net.get("capabilities", "").upper()
        rssi  = net.get("rssi", -100)
        sec, _= parse_security(caps)

        found = []
        if sec == "OPEN":          found.append("OPEN")
        if sec == "WEP":           found.append("WEP")
        if sec == "WPA":           found.append("WPA1")
        if "TKIP" in caps and "CCMP" not in caps: found.append("TKIP")
        if "WPS"  in caps:         found.append("WPS")
        if not net.get("ssid"):    found.append("HIDDEN")

        subtitle = f"[bold white]{ssid}[/bold white]  [muted]{rssi}dBm · {sec}[/muted]"

        if not found:
            console.print(Panel(
                "[good]✓  Sem vulnerabilidades detectadas[/good]",
                title=subtitle, border_style="green", padding=(0, 2)
            ))
        else:
            body = ""
            for v in found:
                desc, sev, style = VULN_MAP.get(v, (v, "?", "muted"))
                body += f"  [{style}]▸ {sev}[/{style}]  {desc}\n"
            console.print(Panel(body.rstrip(), title=subtitle,
                                border_style="red", padding=(0, 2)))

    press_enter()

# ─── 5. Gerador de Senhas ─────────────────────────────────────────────────────
def _entropy(pwd: str) -> float:
    pool = 0
    if any(c.islower() for c in pwd): pool += 26
    if any(c.isupper() for c in pwd): pool += 26
    if any(c.isdigit() for c in pwd): pool += 10
    if any(c in string.punctuation for c in pwd): pool += 32
    return len(pwd) * math.log2(pool) if pool else 0.0

def _strength(bits: float) -> tuple:
    if bits < 40: return "FRACA",      "danger"
    if bits < 60: return "MÉDIA",      "warn"
    if bits < 80: return "FORTE",      "info"
    return           "MUITO FORTE",    "good"

def _gen(length: int, upper: bool, digits: bool, symbols: bool) -> str:
    pool = string.ascii_lowercase
    if upper:   pool += string.ascii_uppercase
    if digits:  pool += string.digits
    if symbols: pool += "!@#$%^&*()-_=+[]{}|;:,.<>?"
    rng = random.SystemRandom()
    while True:
        pwd = "".join(rng.choice(pool) for _ in range(length))
        if upper   and not any(c.isupper() for c in pwd): continue
        if digits  and not any(c.isdigit() for c in pwd): continue
        if symbols and not any(c in string.punctuation for c in pwd): continue
        return pwd

def module_generator():
    header()
    console.print(Panel("[primary]  GERADOR DE SENHAS[/primary]", border_style="red"))
    console.print()

    presets = {
        "1": ("PIN Numérico (8 dígitos)",          8,  False, True,  False),
        "2": ("WPA Padrão (12 chars)",             12,  True,  True,  False),
        "3": ("WPA Forte (16 chars + símbolos)",   16,  True,  True,  True),
        "4": ("Máxima (32 chars + símbolos)",      32,  True,  True,  True),
        "5": ("Personalizado",                      0,  False, False, False),
    }

    for k, (lbl, *_) in presets.items():
        console.print(f"  [secondary]{k}[/secondary]  {lbl}")
    console.print()
    choice = Prompt.ask("[primary]Preset[/primary]", choices=list(presets.keys()), default="3")

    lbl, length, upper, digits, symbols = presets[choice]
    if choice == "5":
        length  = int(Prompt.ask("  Comprimento", default="20"))
        upper   = Confirm.ask("  Maiúsculas?",   default=True)
        digits  = Confirm.ask("  Dígitos?",      default=True)
        symbols = Confirm.ask("  Símbolos?",     default=True)

    count = int(Prompt.ask("  Quantas gerar", default="5"))
    console.print()

    tbl = Table(
        title=f"[primary]{lbl}[/primary]",
        border_style="red", header_style="bold red",
        box=box.HEAVY_EDGE, show_lines=True,
    )
    tbl.add_column("#",        width=4,  justify="right", style="muted")
    tbl.add_column("Senha",    min_width=36, style="bold white")
    tbl.add_column("Entropia", justify="center", width=12)
    tbl.add_column("Força",    justify="center", width=14)

    for i in range(1, count + 1):
        pwd  = _gen(length, upper, digits, symbols)
        bits = _entropy(pwd)
        fl, fs = _strength(bits)
        tbl.add_row(str(i), pwd, f"{bits:.1f} bits", f"[{fs}]{fl}[/{fs}]")

    console.print(tbl)
    press_enter()

# ─── 6. Teste de Conexão ──────────────────────────────────────────────────────
def _ping(host: str, count: int = 4) -> dict:
    import re
    ok, out = run_cmd(f"ping -c {count} -W 2 {host}", timeout=15)
    res = {"host": host, "ok": False, "lat": None, "loss": "100%"}
    m = re.search(r"avg/mdev = [\d.]+/([\d.]+)", out)
    if m: res["lat"] = float(m.group(1))
    m2 = re.search(r"(\d+)% packet loss", out)
    if m2: res["loss"] = m2.group(1) + "%"
    res["ok"] = res["loss"] != "100%"
    return res

def module_connectivity():
    header()
    console.print(Panel("[primary]  TESTE DE CONEXÃO[/primary]", border_style="red"))
    console.print()

    ok, raw = run_cmd("termux-wifi-connectioninfo", timeout=10)
    if ok and raw.strip().startswith("{"):
        try:
            info = json.loads(raw)
            console.print(Panel(
                f"[bold white]SSID:[/bold white]        {info.get('ssid','?')}\n"
                f"[bold white]BSSID:[/bold white]       {info.get('bssid','?')}\n"
                f"[bold white]IP:[/bold white]          {info.get('ip','?')}\n"
                f"[bold white]Sinal:[/bold white]       {info.get('rssi','?')} dBm\n"
                f"[bold white]Link Speed:[/bold white]  {info.get('link_speed_mbps','?')} Mbps",
                title="[primary]Rede Atual[/primary]",
                border_style="red", padding=(0, 2)
            ))
            console.print()
        except Exception:
            pass

    targets = [("8.8.8.8","Google DNS"),("1.1.1.1","Cloudflare"),("8.8.4.4","Google DNS #2")]

    tbl = Table(
        title="[primary]Ping Tests[/primary]",
        border_style="red", header_style="bold red",
        box=box.HEAVY_EDGE, show_lines=True,
    )
    tbl.add_column("Host",     min_width=14)
    tbl.add_column("Serviço",  width=14)
    tbl.add_column("Status",   justify="center", width=10)
    tbl.add_column("Latência", justify="right",  width=12)
    tbl.add_column("Perda",    justify="center", width=8)

    with Progress(SpinnerColumn(style="red"),
                  TextColumn("[secondary]{task.description}[/secondary]"),
                  console=console, transient=True) as p:
        for host, lbl in targets:
            task = p.add_task(f"Ping {host}...", total=None)
            r = _ping(host)
            p.remove_task(task)
            st  = "[good]ONLINE[/good]" if r["ok"] else "[danger]OFFLINE[/danger]"
            lat = f"{r['lat']:.1f} ms" if r["lat"] else "[muted]—[/muted]"
            tbl.add_row(host, lbl, st, lat, r["loss"])

    console.print(tbl)

    console.print("\n[muted]  Testando HTTP...[/muted]")
    try:
        t0 = time.time()
        resp = _requests.get("https://www.google.com", timeout=8)
        ms   = (time.time() - t0) * 1000
        console.print(f"  [good]HTTP OK[/good]  {resp.status_code}  [muted]{ms:.0f}ms[/muted]")
    except Exception as e:
        console.print(f"  [danger]HTTP FAIL[/danger]  {e}")

    press_enter()

# ─── 7. Relatórios ────────────────────────────────────────────────────────────
def module_reports():
    header()
    console.print(Panel("[primary]  GERADOR DE RELATÓRIOS[/primary]", border_style="red"))
    console.print("[muted]  Coletando dados...[/muted]\n")

    networks = []
    with Progress(SpinnerColumn(style="red"),
                  TextColumn("[secondary]{task.description}[/secondary]"),
                  console=console, transient=True) as p:
        p.add_task("Scan...", total=None)
        networks = wifi_scan()
        time.sleep(0.8)

    now = datetime.datetime.now()
    ts  = now.strftime("%Y%m%d_%H%M%S")
    RDIR.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at":   now.isoformat(),
        "total_networks": len(networks),
        "risk_summary":   {"CRÍTICO":0,"ALTO":0,"MÉDIO":0,"BAIXO":0},
        "networks":       [],
    }

    for net in networks:
        caps  = net.get("capabilities","").upper()
        sec,_ = parse_security(caps)
        vulns = []
        if sec == "OPEN":           vulns.append("Rede aberta")
        if sec == "WEP":            vulns.append("WEP obsoleto")
        if "WPS" in caps:           vulns.append("WPS ativo")
        if "TKIP" in caps:          vulns.append("TKIP")
        if not net.get("ssid"):     vulns.append("SSID oculto")

        risk = "CRÍTICO" if sec in ("OPEN","WEP") else \
               "ALTO"    if vulns                 else \
               "MÉDIO"   if sec == "WPA2"         else "BAIXO"

        report["risk_summary"][risk] += 1
        report["networks"].append({
            "ssid":            net.get("ssid") or "(oculta)",
            "bssid":           net.get("bssid",""),
            "rssi":            net.get("rssi",0),
            "quality":         rssi_quality(net.get("rssi",-100)),
            "channel":         freq_to_channel(net.get("frequency",0)),
            "security":        sec,
            "risk":            risk,
            "vulnerabilities": vulns,
        })

    jp = RDIR / f"wifimaster_{ts}.json"
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    lines = [
        "═"*60,
        "  WiFi Master — Relatório de Auditoria",
        f"  Gerado em: {now.strftime('%d/%m/%Y %H:%M:%S')}",
        "═"*60,
        f"\n  Total: {len(networks)} redes",
        *[f"  {k}: {v}" for k, v in report["risk_summary"].items()],
        "\n" + "─"*60 + "\n  REDES\n" + "─"*60,
    ]
    for n in report["networks"]:
        lines += [
            f"\n  SSID:  {n['ssid']}",
            f"  BSSID: {n['bssid']}",
            f"  Sinal: {n['rssi']} dBm ({n['quality']}%)",
            f"  Canal: {n['channel']}",
            f"  Seg:   {n['security']} → {n['risk']}",
            *(["  Vulns: " + " | ".join(n["vulnerabilities"])] if n["vulnerabilities"] else []),
        ]
    tp = RDIR / f"wifimaster_{ts}.txt"
    tp.write_text("\n".join(lines), encoding="utf-8")

    console.print(Panel(
        f"[good]✓ JSON:[/good]  {jp}\n[good]✓ TXT:[/good]   {tp}",
        title="[primary]Relatório Salvo[/primary]",
        border_style="green", padding=(0, 2)
    ))
    console.print(f"\n[muted]  Redes: {len(networks)}  |  Críticos: {report['risk_summary']['CRÍTICO']}[/muted]")
    press_enter()

# ─── Menu Principal ───────────────────────────────────────────────────────────
MENU = [
    ("1","Scanner Wi-Fi",              "Detecta redes próximas"),
    ("2","Auditoria de Segurança",     "Protocolos e riscos"),
    ("3","Gerenciador de Senhas",      "Redes salvas (root)"),
    ("4","Análise de Vulnerabilidades","Vetores por rede"),
    ("5","Gerador de Senhas",          "Senhas fortes + entropia"),
    ("6","Teste de Conexão",           "Latência e qualidade"),
    ("7","Relatórios",                 "Exporta JSON + TXT"),
    ("0","Sair",                       ""),
]
DISPATCH = {
    "1": module_scanner, "2": module_audit,   "3": module_passwords,
    "4": module_vulns,   "5": module_generator,"6": module_connectivity,
    "7": module_reports,
}

def main():
    while True:
        header()
        tbl = Table(box=box.HEAVY_EDGE, border_style="red",
                    show_header=False, padding=(0, 3), expand=False)
        tbl.add_column(width=4, justify="right")
        tbl.add_column(min_width=28)
        tbl.add_column(style="muted", min_width=24)

        for key, name, desc in MENU:
            if key == "0":
                tbl.add_row(f"[muted]{key}[/muted]", f"[muted]{name}[/muted]", "")
            else:
                tbl.add_row(f"[secondary]{key}[/secondary]",
                            f"[bold white]{name}[/bold white]", desc)

        console.print(Align.center(tbl))
        console.print()
        choice = Prompt.ask("[primary]  →[/primary]", default="0")

        if choice == "0":
            clear()
            console.print("[muted]  Saindo.[/muted]")
            sys.exit(0)

        fn = DISPATCH.get(choice)
        if fn:
            fn()
        else:
            console.print("[danger]  Opção inválida.[/danger]")
            time.sleep(0.7)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: (
        console.print("\n[muted]  Interrompido.[/muted]"), sys.exit(0)
    ))
    main()