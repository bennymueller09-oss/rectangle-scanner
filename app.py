import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import urllib.request
import json
import time
from datetime import datetime

st.set_page_config(
    page_title="Rectangle Scanner",
    page_icon="🟦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: #1a1d2e; border: 1px solid #2a2d45;
    border-radius: 12px; padding: 16px 20px;
}
div[data-testid="metric-container"] label { color: #9ca3af !important; font-size: 13px !important; }
div[data-testid="metric-container"] [data-testid="metric-value"] {
    color: #f9fafb !important; font-size: 26px !important; font-weight: 600 !important;
}
[data-testid="stSidebar"] { background: #0d1117; border-right: 1px solid #21262d; }
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span { color: #c9d1d9 !important; }
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid #21262d; }
hr { border-color: #21262d !important; }
</style>
""", unsafe_allow_html=True)

# ── Telegram & Secrets ───────────────────────────────────────────────────────
try:
    TELEGRAM_TOKEN   = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except Exception:
    TELEGRAM_TOKEN   = ""
    TELEGRAM_CHAT_ID = ""

def send_telegram(text, emoji=""):
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data,
              headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False

# ── Monitoring: Fehler nur einmal pro Session melden ─────────────────────────
def monitor_fehler(fehler_typ, details=""):
    """
    Schickt eine Telegram-Warnung — aber maximal einmal pro Fehlertyp pro Session.
    Verhindert Spam bei wiederholten Fehlern.
    """
    if "gemeldete_fehler" not in st.session_state:
        st.session_state["gemeldete_fehler"] = set()
    if fehler_typ in st.session_state["gemeldete_fehler"]:
        return  # Bereits gemeldet — kein Spam
    st.session_state["gemeldete_fehler"].add(fehler_typ)
    now = datetime.now().strftime("%H:%M:%S")

    nachrichten = {
        "DATEN_FEHLER": (
            f"⚠️ <b>Datenfehler — Rectangle Scanner</b>\n\n"
            f"Mehr als 20% der Aktien konnten nicht geladen werden.\n"
            f"Mögliche Ursache: yfinance API Problem oder Markt geschlossen.\n"
            f"Details: {details}\n🕐 {now}"
        ),
        "SCAN_ABSTURZ": (
            f"🔴 <b>Scanner-Absturz — Rectangle Scanner</b>\n\n"
            f"Ein unerwarteter Fehler ist aufgetreten:\n"
            f"<code>{details}</code>\n🕐 {now}"
        ),
        "KEIN_KURS": (
            f"⚠️ <b>Kursdaten fehlen — Rectangle Scanner</b>\n\n"
            f"Aktie: <b>{details}</b> liefert keine Kursdaten.\n"
            f"Möglicherweise außerhalb der Handelszeiten oder delistet.\n🕐 {now}"
        ),
        "SECRETS_FEHLEN": (
            f"🔐 <b>Secrets fehlen — Rectangle Scanner</b>\n\n"
            f"Telegram-Token nicht in Streamlit Secrets gefunden!\n"
            f"Bitte Secrets in Streamlit Cloud prüfen.\n🕐 {now}"
        ),
        "HOHE_FEHLERQUOTE": (
            f"📉 <b>Hohe Fehlerquote — Rectangle Scanner</b>\n\n"
            f"<b>{details}</b> Aktien konnten nicht gescannt werden.\n"
            f"Scanner läuft weiter — bitte prüfen ob Markt offen ist.\n🕐 {now}"
        ),
    }
    msg = nachrichten.get(fehler_typ, f"⚠️ Unbekannter Fehler: {fehler_typ}\n{details}\n🕐 {now}")
    send_telegram(msg)

def markt_offen():
    """
    Prüft ob der US-Markt gerade offen ist.
    US-Markt: Mo–Fr 15:30–22:00 Uhr DE-Zeit (MEZ/MESZ)
    """
    now  = datetime.now()
    wday = now.weekday()          # 0=Mo, 4=Fr, 5=Sa, 6=So
    hour = now.hour
    minute = now.minute
    if wday >= 5:                 # Wochenende
        return False
    time_now = hour * 60 + minute
    # 15:30 = 930 min, 22:00 = 1320 min
    return 930 <= time_now <= 1320

def monitor_ok_nachricht():
    """
    Tägliche Bestätigung — robust gegen App-Neustarts auf Streamlit Cloud.
    Nutzt /tmp Datei statt Session-State (überlebt App-Neustarts nicht,
    aber wird beim ersten Scan nach Marktöffnung zuverlässig ausgelöst).
    """
    if not markt_offen():
        return
    import os
    heute      = datetime.now().strftime("%Y-%m-%d")
    flag_file  = f"/tmp/rect_ok_{heute}.flag"
    if os.path.exists(flag_file):
        return
    try:
        open(flag_file, "w").close()
    except Exception:
        pass
    now = datetime.now().strftime("%H:%M:%S")
    send_telegram(
        f"✅ <b>Rectangle Scanner läuft</b>\n\n"
        f"Erster Scan des Tages abgeschlossen.\n"
        f"342 Aktien werden überwacht.\n"
        f"🕐 {now}"
    )

# ── Watchlist ─────────────────────────────────────────────────────────────────
WATCHLIST = [
    "AAL","AAPL","ABBV","ABNB","ABT","ACN","ADBE","ADI","ADM","ADP","ADSK",
    "AEP","AES","AFL","AIG","AIZ","AJG","ALK","ALLE","AMAT","AMD","AME",
    "AMGN","AMT","AMZN","ANET","ANSS","AON","AOS","APA","APD","APH","ASML",
    "AVGO","AXP","AZN","AZO","BA","BAC","BBWI","BDX","BEN","BIIB","BK",
    "BKNG","BKR","BLK","BMY","BSX","BWA","BX","C","CAG","CARR","CAT","CB",
    "CCEP","CDNS","CDW","CEG","CHD","CHRW","CHTR","CI","CINF","CL","CMA",
    "CMCSA","CME","CMG","CMI","COF","COP","COST","CPB","CPRT","CPT","CRM",
    "CRWD","CSCO","CSGP","CSX","CTAS","CTSH","CVS","CVX","DAL","DASH","DD",
    "DDOG","DE","DHI","DHR","DIS","DLTR","DOW","DUK","DVA","DXCM","EA",
    "EBAY","ECL","EIX","ELV","EMN","EMR","ENPH","EOG","EQIX","ETN","ETSY",
    "EVRG","EW","EXC","FANG","FAST","FCX","FDX","FFIV","FI","FMC","FSLR",
    "FTNT","GD","GE","GEHC","GEN","GFS","GILD","GIS","GLW","GM","GNRC",
    "GOOG","GOOGL","GS","GWW","HAL","HAS","HCA","HD","HES","HII","HLT",
    "HON","HPE","HPQ","HRL","HSIC","HSY","HUM","IBM","ICE","IDXX","IEX",
    "ILMN","INTC","INTU","IP","IPG","ISRG","ITW","IVZ","JCI","JD","JKHY",
    "JNJ","JNPR","JPM","K","KDP","KEY","KHC","KLAC","KMX","KO","KR","L",
    "LEN","LHX","LIN","LKQ","LLY","LMT","LOW","LRCX","LULU","LYB","LYV",
    "MA","MAR","MCD","MCHP","MCK","MCO","MDB","MDLZ","MDT","MELI","MET",
    "META","MGM","MHK","MKTX","MLM","MMC","MMM","MNST","MO","MOS","MPC",
    "MRK","MRNA","MRO","MRVL","MS","MSCI","MSFT","MSI","MTCH","MU","NCLH",
    "NEE","NEM","NFLX","NI","NKE","NOC","NOW","NRG","NSC","NUE","NVDA",
    "NWS","NWSA","NXPI","ODFL","ON","ORCL","ORLY","OXY","PANW","PARA",
    "PAYC","PAYX","PCAR","PDD","PEG","PEP","PFE","PG","PGR","PH","PHM",
    "PLD","PM","PNC","PNR","PPG","PRU","PSA","PSX","PYPL","QCOM","QRVO",
    "RCL","REGN","RHI","RL","ROK","ROL","ROP","ROST","RTX","RVTY","SBUX",
    "SCHW","SEE","SHW","SIRI","SJM","SLB","SNPS","SO","SPGI","SPLK","SRE",
    "STT","STX","STZ","SYK","SYY","T","TAP","TDG","TEAM","TGT","TJX",
    "TMO","TMUS","TPR","TRV","TSLA","TSN","TT","TTD","TTWO","TXN","UAL",
    "UDR","UHS","UNH","UNP","UPS","USB","V","VFC","VLO","VRSK","VRTX",
    "VTRS","VZ","WAB","WBA","WBD","WDAY","WDC","WEC","WELL","WFC","WHR",
    "WM","WMT","WYNN","XEL","XOM","XRAY","YUM","ZBRA","ZION","ZS","ZTS",
]

# ── Datenabruf ────────────────────────────────────────────────────────────────
def normalize_df(df):
    if df is None or df.empty: return None
    cols = {c: (c[0] if isinstance(c, tuple) else c) for c in df.columns}
    df   = df.rename(columns=cols)
    return df.loc[:, ~df.columns.duplicated()]

@st.cache_data(ttl=60)
def get_data(ticker):
    for attempt in range(3):
        try:
            time.sleep(0.5)
            df = yf.download(ticker, period="1d", interval="1m",
                             progress=False, auto_adjust=True, threads=False)
            df = normalize_df(df)
            if df is None or len(df) < 10:
                time.sleep(2); continue
            return df
        except Exception:
            if attempt < 2: time.sleep(3)
    return None

@st.cache_data(ttl=3600)
def get_volumen(ticker):
    """Holt das durchschnittliche Tagesvolumen der letzten 5 Tage."""
    try:
        time.sleep(0.3)
        df = yf.download(ticker, period="5d", interval="1d",
                         progress=False, auto_adjust=True, threads=False)
        df = normalize_df(df)
        if df is None or df.empty: return 0
        return int(df["Volume"].values.flatten().astype(float).mean())
    except Exception:
        return 0

@st.cache_data(ttl=300)
def get_vix():
    for attempt in range(3):
        try:
            time.sleep(0.3)
            df = yf.download("^VIX", period="1d", interval="5m",
                             progress=False, auto_adjust=True, threads=False)
            df = normalize_df(df)
            if df is None or df.empty:
                time.sleep(2); continue
            return round(float(df["Close"].values.flatten().astype(float)[-1]), 2)
        except Exception:
            if attempt < 2: time.sleep(3)
    return None

# ── Setup-Erkennung ───────────────────────────────────────────────────────────
def check_setup(df, p, volumen=0):
    n  = len(df)
    lb = min(p["lookback"],   max(n // 3, 5))
    ml = min(p["mom_kerzen"], max(n - lb - 1, 5))
    r  = dict(momentum=False, rectangle=False, ein_drittel=False,
              tageshoch=False, seitwaerts=False, auflagen=False,
              liquiditaet=False, kurs_ok=False, kein_gap=False, tp_ok=False,
              hi=0.0, lo=0.0, range_pct=0.0, corr_pct=0.0,
              touch_res=0, touch_sup=0, mom_pct=0.0, kurs=0.0,
              richtung="LONG", erfuellt=0, status="NEIN")
    try:
        if n < lb + ml: return r
        recent = df.iloc[-lb:]
        prior  = df.iloc[-(lb + ml):-lb]
        if prior.empty or recent.empty: return r

        hi   = float(recent["High"].values.flatten().astype(float).max())
        lo   = float(recent["Low"].values.flatten().astype(float).min())
        kurs = float(df["Close"].values.flatten().astype(float)[-1])
        rng  = (hi - lo) / lo * 100 if lo > 0 else 0
        r.update(hi=hi, lo=lo, range_pct=round(rng,2), kurs=round(kurs,2))

        # ── Tageshoch bestimmen für Richtung ──────────────────────────────────
        dh = float(df["High"].values.flatten().astype(float).max())
        dl = float(df["Low"].values.flatten().astype(float).min())
        nahe_hoch = hi >= dh * (1 - p["near_high_pct"]/100)
        nahe_tief = lo <= dl * (1 + p["near_high_pct"]/100)
        r["tageshoch"] = nahe_hoch or nahe_tief
        r["richtung"]  = "LONG" if nahe_hoch else "SHORT"

        # ── Kriterium: Liquidität (Volumen > 1 Mio/Tag) ───────────────────────
        r["liquiditaet"] = volumen >= p["min_volumen"]

        # ── Kriterium: Kurs > $5 (kein Penny Stock) ───────────────────────────
        r["kurs_ok"] = kurs >= p["min_kurs"]

        # ── Kriterium: Keine Intraday-Gaps im M1 Chart ────────────────────────
        closes  = df["Close"].values.flatten().astype(float)
        opens   = df["Open"].values.flatten().astype(float)
        max_gap = 0.0
        for j in range(1, len(closes)):
            if closes[j-1] > 0:
                gap_pct = abs(opens[j] - closes[j-1]) / closes[j-1] * 100
                max_gap = max(max_gap, gap_pct)
        r["kein_gap"] = max_gap < p["max_gap_pct"]

        # ── Momentum ──────────────────────────────────────────────────────────
        ph = float(prior["High"].values.flatten().astype(float).max())
        pl = float(prior["Low"].values.flatten().astype(float).min())
        mp = max((ph-pl)/pl*100 if pl>0 else 0, (ph-pl)/ph*100 if ph>0 else 0)
        r["mom_pct"]   = round(mp, 2)
        cv = prior["Close"].values.flatten().astype(float)
        r["momentum"]  = mp >= p["min_mom_pct"] and float(cv[-1]) != float(cv[0])
        r["rectangle"] = rng < p["max_range_pct"]

        # ── 1/3 Regel ─────────────────────────────────────────────────────────
        ms = ph - pl; rs = hi - lo
        cp = (rs/ms*100) if ms > 0 else 100
        r["corr_pct"]    = round(cp, 1)
        r["ein_drittel"] = cp < p["max_corr_pct"]

        # ── TP-Mindestabstand $0.10 ────────────────────────────────────────────
        # Rectangle-Breite muss mind. $0.10 betragen (sonst zu ruhige Aktie)
        rect_breite_dollar = hi - lo
        r["tp_ok"] = rect_breite_dollar >= p["min_tp_abstand"]

        # ── Seitwärts-Check (inkl. Dreieck-Filter) ────────────────────────────
        half = max(lb//2, 3)
        if len(recent) > half:
            he = float(recent.iloc[:half]["High"].values.flatten().astype(float).max())
            hl = float(recent.iloc[half:]["High"].values.flatten().astype(float).max())
            le = float(recent.iloc[:half]["Low"].values.flatten().astype(float).min())
            ll = float(recent.iloc[half:]["Low"].values.flatten().astype(float).min())
            # Flache Hochs und Tiefs = Seitwärts (kein Dreieck, keine Flagge)
            highs_flat = abs(hl-he)/hi*100 < p["sideways_tol"]
            lows_flat  = abs(ll-le)/lo*100 < p["sideways_tol"]
            # Dreieck-Filter: Highs dürfen nicht fallen UND Lows dürfen nicht steigen
            kein_dreieck = not (hl < he * 0.999 and ll > le * 1.001)
            r["seitwaerts"] = highs_flat and lows_flat and kein_dreieck

        # ── Auflagen — richtungsabhängig laut PDF ─────────────────────────────
        # Long: primär obere Linie zählt (Widerstand)
        # Short: primär untere Linie zählt (Support)
        tol = p["touch_tol"] / 100
        r["touch_res"] = int((recent["High"].values.flatten().astype(float) >= hi*(1-tol)).sum())
        r["touch_sup"] = int((recent["Low"].values.flatten().astype(float)  <= lo*(1+tol)).sum())
        if r["richtung"] == "LONG":
            # Long: obere Trendlinie muss mind. 2 Auflagen haben
            r["auflagen"] = r["touch_res"] >= p["min_touches"]
        else:
            # Short: untere Trendlinie muss mind. 2 Auflagen haben
            r["auflagen"] = r["touch_sup"] >= p["min_touches"]

        # ── Alle Kriterien summieren ───────────────────────────────────────────
        erf = sum([r["momentum"], r["rectangle"], r["ein_drittel"],
                   r["tageshoch"], r["seitwaerts"], r["auflagen"],
                   r["liquiditaet"], r["kurs_ok"], r["kein_gap"], r["tp_ok"]])
        r["erfuellt"] = erf
        # Setup nur wenn alle 10 Kriterien erfüllt
        r["status"] = "SETUP ✓" if erf==10 else "FAST" if erf>=7 else "NEIN"
    except Exception:
        r["status"] = "FEHLER"
    return r

# ── Hauptfunktion ─────────────────────────────────────────────────────────────
def main():
    # Secrets prüfen — sofort melden wenn fehlen
    if not TELEGRAM_TOKEN:
        st.error("⛔ Telegram Secrets fehlen — Alerts deaktiviert!")
        monitor_fehler("SECRETS_FEHLEN")

    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.title("🟦 Rectangle Scanner")
        st.caption("Momentum-Konsolidierung am Tageshoch · 1-Minuten-Chart · 342 Aktien")
    with col_h2:
        st.metric("🕐 Uhrzeit", datetime.now().strftime("%H:%M:%S"))

    with st.sidebar:
        st.markdown("### ⚙️ Parameter")
        p = {
            "lookback":        st.slider("Lookback Kerzen",         5,   60,  20),
            "max_range_pct":   st.slider("Max. Range %",            0.2, 3.0, 1.5, 0.1),
            "min_touches":     st.slider("Min. Auflagepunkte",      2,   5,   2),
            "min_mom_pct":     st.slider("Min. Momentum %",         0.5, 5.0, 1.5, 0.1),
            "max_corr_pct":    st.slider("Max. Korrektur %",        10,  50,  33),
            "sideways_tol":    st.slider("Seitwärts Toleranz %",    0.1, 1.0, 0.4, 0.05),
            "min_volumen":     st.number_input("Min. Volumen/Tag", value=1_000_000, step=500_000),
            "min_kurs":        st.slider("Min. Kurs ($)",           1.0, 20.0, 5.0, 0.5),
            "max_gap_pct":     st.slider("Max. Gap % (M1)",         0.01, 0.5, 0.05, 0.01),
            "min_tp_abstand":  st.slider("Min. TP-Abstand ($)",     0.05, 0.5, 0.10, 0.05),
            "mom_kerzen": 30, "touch_tol": 0.05, "near_high_pct": 0.5,
        }
        st.divider()
        st.markdown("### 🔔 Telegram Alerts")
        tg_aktiv = st.toggle("Benachrichtigungen aktiv", value=True)
        st.caption("@Rectangelbot")
        if st.button("🧪 Test-Nachricht senden"):
            ok = send_telegram("🧪 <b>Test</b> — Rectangle Scanner läuft!")
            st.success("✅ Gesendet!") if ok else st.error("❌ Fehler — Secrets prüfen")
        st.divider()
        st.markdown("### 📋 Watchlist")
        custom    = st.text_area("Ticker (eine pro Zeile)", "\n".join(WATCHLIST), height=160)
        watchlist = [t.strip().upper() for t in custom.split("\n") if t.strip()]
        st.caption(f"**{len(watchlist)}** Aktien")
        st.divider()
        auto_ref = st.toggle("🔄 Auto-Refresh (1 min)", value=True)
        st.caption("🕐 US-Markt: 15:30 – 22:00 Uhr DE")

    # VIX
    vix = get_vix()
    if vix:
        if vix >= 30:
            st.error(f"⛔ VIX {vix} — Sehr hohe Volatilität!")
        elif vix >= 20:
            st.warning(f"⚡ VIX {vix} — Erhöhte Volatilität.")
        else:
            st.success(f"✅ VIX {vix} — Ruhiger Markt.")
    st.divider()

    # Session State initialisieren
    if "gemeldet"        not in st.session_state: st.session_state["gemeldet"]        = set()
    if "gemeldete_fehler" not in st.session_state: st.session_state["gemeldete_fehler"] = set()
    if "letzter_ok_tag"  not in st.session_state: st.session_state["letzter_ok_tag"]  = ""

    # Scan
    rows, neue_setups, fehler_ticker = [], [], []
    progress = st.progress(0, text="Scanner läuft …")

    try:
        for i, ticker in enumerate(watchlist):
            progress.progress((i+1)/len(watchlist), f"Scanne {ticker} … ({i+1}/{len(watchlist)})")
            df = get_data(ticker)

            if df is None:
                fehler_ticker.append(ticker)
                rows.append({"Aktie":ticker,"Kurs":"–","Richtung":"–","Status":"FEHLER",
                             "Momentum":"✗","Rectangle":"✗","1/3 Regel":"✗",
                             "Tageshoch":"✗","Seitwärts":"✗","Auflagen":"✗",
                             "Liquidität":"✗","Kurs>$5":"✗","Kein Gap":"✗","TP≥$0.10":"✗",
                             "Range %":"–","Korrektur %":"–","R/S":"–","Erfüllt":0})
                continue

            vol = get_volumen(ticker)
            r   = check_setup(df, p, volumen=vol)

            # Setup-Alert
            if tg_aktiv and r["status"] == "SETUP ✓" and ticker not in st.session_state["gemeldet"]:
                st.session_state["gemeldet"].add(ticker)
                neue_setups.append(ticker)
                now_s = datetime.now().strftime("%H:%M:%S")
                send_telegram(
                    f"🟦 <b>RECTANGLE SETUP ✅</b>\n"
                    f"<b>{ticker}</b> — alle 6 Kriterien erfüllt\n"
                    f"Kurs: <b>${r['kurs']}</b>\n"
                    f"Momentum: {r['mom_pct']}%  |  Range: {r['range_pct']}%\n"
                    f"Korrektur: {r['corr_pct']}%\n🕐 {now_s}"
                )
            if r["status"] != "SETUP ✓":
                st.session_state["gemeldet"].discard(ticker)

            rows.append({
                "Aktie":       ticker,
                "Kurs":        f"${r['kurs']}",
                "Richtung":    r["richtung"],
                "Status":      r["status"],
                "Momentum":    "✓" if r["momentum"]    else "✗",
                "Rectangle":   "✓" if r["rectangle"]   else "✗",
                "1/3 Regel":   "✓" if r["ein_drittel"] else "✗",
                "Tageshoch":   "✓" if r["tageshoch"]   else "✗",
                "Seitwärts":   "✓" if r["seitwaerts"]  else "✗",
                "Auflagen":    "✓" if r["auflagen"]    else "✗",
                "Liquidität":  "✓" if r["liquiditaet"] else "✗",
                "Kurs>$5":     "✓" if r["kurs_ok"]    else "✗",
                "Kein Gap":    "✓" if r["kein_gap"]   else "✗",
                "TP≥$0.10":    "✓" if r["tp_ok"]      else "✗",
                "Range %":     f"{r['range_pct']}%",
                "Korrektur %": f"{r['corr_pct']}%",
                "R/S":         f"R:{r['touch_res']}  S:{r['touch_sup']}",
                "Erfüllt":     r["erfuellt"],
            })

        # ── Monitoring: Fehlerquote prüfen ────────────────────────────────────
        fehler_pct = len(fehler_ticker) / max(len(watchlist), 1) * 100
        if fehler_pct > 30 and markt_offen():
            monitor_fehler("HOHE_FEHLERQUOTE",
                           f"{len(fehler_ticker)} von {len(watchlist)} Aktien")

        # ── Monitoring: Tägliche OK-Meldung ──────────────────────────────────
        if tg_aktiv and fehler_pct <= 30:
            monitor_ok_nachricht()

    except Exception as e:
        monitor_fehler("SCAN_ABSTURZ", str(e)[:200])
        st.error(f"⛔ Scan-Fehler: {e}")
        st.stop()

    progress.empty()
    if neue_setups:
        st.balloons()
        st.success(f"🔔 Telegram Alert gesendet für: {', '.join(neue_setups)}")

    df_all  = pd.DataFrame(rows)
    scan_ts = datetime.now().strftime("%H:%M:%S")

    # Metriken
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("📊 Gescannt",     len(df_all))
    c2.metric("✅ Setup",         len(df_all[df_all["Status"]=="SETUP ✓"]))
    c3.metric("🔎 Fast",          len(df_all[df_all["Status"]=="FAST"]))
    c4.metric("⚠️ Fehler",        len(fehler_ticker))
    c5.metric("🔔 Aktive Alerts", len(st.session_state["gemeldet"]))
    c6.metric("🕐 Scan um",       scan_ts)
    st.divider()

    # Fehler-Warnung bei vielen Fehlern
    if len(fehler_ticker) > 0:
        pct = round(len(fehler_ticker)/len(watchlist)*100, 1)
        if pct > 30:
            st.error(f"⚠️ {len(fehler_ticker)} Aktien nicht ladbar ({pct}%) — Markt möglicherweise geschlossen.")
        else:
            st.warning(f"ℹ️ {len(fehler_ticker)} Aktien nicht ladbar ({pct}%) — normal außerhalb der Handelszeiten.")

    # Ergebnisse
    df_setup = df_all[df_all["Status"]=="SETUP ✓"]
    if not df_setup.empty:
        st.subheader(f"✅ Vollständiges Setup ({len(df_setup)})")
        st.dataframe(df_setup.drop(columns=["Erfüllt"]), use_container_width=True, hide_index=True)
    else:
        st.info("📭 Aktuell kein vollständiges Rectangle-Setup.")

    df_fast = df_all[df_all["Status"]=="FAST"].sort_values("Erfüllt", ascending=False)
    if not df_fast.empty:
        st.subheader(f"🔎 Fast erfüllt — beobachten ({len(df_fast)})")
        st.dataframe(df_fast.drop(columns=["Erfüllt"]), use_container_width=True, hide_index=True)

    with st.expander(f"📋 Alle {len(df_all)} Aktien"):
        st.dataframe(df_all.sort_values("Erfüllt", ascending=False).drop(columns=["Erfüllt"]),
                     use_container_width=True, hide_index=True)

    with st.expander("📖 Kriterien"):
        st.markdown("""
| # | Kriterium | Beschreibung |
|---|-----------|-------------|
| 1 | **Momentum** | Starker Trend vor dem Rectangle (Aufwärts oder Abwärts) |
| 2 | **Rectangle** | Enge Konsolidierungszone (Max. Range % einstellbar) |
| 3 | **1/3 Regel** | Korrektur max. 33% der Momentumbewegung |
| 4 | **Tageshoch** | Rectangle am Tageshoch (Long) oder Tagestief (Short) |
| 5 | **Seitwärts** | Flache Hochs und Tiefs — kein Dreieck, keine Flagge |
| 6 | **Auflagen** | Long: min. 2× obere Linie berührt · Short: min. 2× untere Linie |
| 7 | **Liquidität** | Volumen > 1 Mio/Tag (kein illiquider Titel) |
| 8 | **Kurs > $5** | Kein Penny Stock |
| 9 | **Kein Gap** | Keine Intraday-Gaps im M1 Chart |
| 10 | **TP ≥ $0.10** | Rectangle breit genug für sinnvollen Take-Profit |
        """)

    if auto_ref:
        # Keep-Alive: verhindert App-Einschlafen auf Streamlit Cloud
        import os
        ka_file = "/tmp/rect_keepalive.txt"
        try:
            with open(ka_file, "w") as f:
                f.write(datetime.now().isoformat())
        except Exception:
            pass
        time.sleep(90)
        st.rerun()

if __name__ == "__main__":
    main()
