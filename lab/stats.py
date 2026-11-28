#!/usr/bin/env python3
"""Lab de Trader OS: qué combinación de estrategia + entrada + stop + salida
+ confluencia funciona mejor, medido solo con data propia.

Fuentes (nada de Yahoo):
  tvbars/<dia>.json   velas de 5m de TradingView que manda el TDL Feed (FEED1) con su contexto
                      por vela: VWAP, EMA 20/50/200, EMA 1h, niveles de sesión, chop, estiramiento...
  events/<dia>.jsonl  TDL KL (régimen, alineación, toques de niveles) y los SUMMARY de los
                      indicadores LAB (paridad)
  plans/              plan pre-NY de Trader OS (sesgo por símbolo)

Familias (cada una con su rejilla de variantes, ver config.json):
  ORB   ruptura del rango de apertura · ventanas 5/15/30 · entrada al cierre o en retest ·
        stop lado opuesto / medio / borde · salida 1R, 2R, 3R, 1x rango, cierre del día
  IBB   ruptura del Initial Balance · misma rejilla con el rango del IB
  IBL   reacción a niveles internos/extensiones del IB (-50..150 %) · límite en el nivel ·
        stop 0.1 / 0.25 IB · 1R, 2R o el siguiente nivel; con niveles de control (12.5, 37.5...)
  SWR   barrida de Asia / Londres / ON / PDH-PDL y reclaim → reversa
  SWC   barrida aceptada (2 cierres fuera) → continuación
  VA80  regla del 80 %: abre fuera del value area de ayer, vuelve a entrar → hacia el otro lado;
        control = % de días que tocan los dos bordes del VA de todos modos
  RIF   rango (como TDL PA) → ruptura → cierre que invierte el FVG en contra (iFVG) · entrada al
        cierre, retest del iFVG (borde o CE) o del borde del rango; a cualquier hora del día
  RBO   la misma ruptura de rango sola: comparación para ver si el iFVG aporta
  ZON   zonas de Mi Mesa: límite en la entrada de toda zona tocada (sin el filtro de 'armada', que se
        conoce después) frente a entrar en el gatillo; stop de la zona; TP1, 1R, 2R o fin de ventana
  PB    retroceso a EMA20 / VWAP de 5m · límite o cierre de rechazo · stop swing / 0.5 ATR ·
        1R, 2R o máximo del día; trendTest compara tendencia 1h a favor frente a en contra

Cada operación lleva su foto de confluencias en la vela de la señal, relativa a la dirección
(favor / contra): VWAP, EMAs, EMA200, HTF 1h, régimen y alineación de TDL KL, plan pre-NY, chop,
estiramiento, premium/discount, SMT, gap, hora y día. El ranking usa R neto (costTicks por
operación) y ordena por el límite inferior (expR - 1 error típico) para no premiar la suerte.

Reglas de simulación (conservadoras): stop y target en la misma vela = stop; en la vela del
llenado de un límite solo cuenta el stop; sin salida al cierre NY = se cierra a mercado.

Uso:  python3 lab/stats.py [--dry]
Python 3.11 stdlib.
"""
import bisect
import datetime as dt
import glob
import json
import math
import os
import random
import zlib
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NY = ZoneInfo("America/New_York")
BAR = 300
FEATS = ["vwap", "ema", "ema200", "htf", "klRegime", "klAlign", "plan", "chop", "stretch",
         "zone", "smt", "gap", "time", "dow"]


def load_cfg():
    with open(os.path.join(ROOT, "lab", "config.json"), encoding="utf-8") as f:
        return json.load(f)


def norm_sym(raw, cfg):
    if not raw:
        return None
    s = str(raw).upper().split(":")[-1]
    for suf in ("1!", "2!"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return cfg["aliases"].get(s, s)


def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ================================================================ carga

def load_tvbars(cfg):
    """{sym: [bar dict]} ordenado; bar['t'] en segundos (apertura)."""
    by = defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(ROOT, "tvbars", "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        fields = d.get("fields") or []
        for raw, rows in (d.get("symbols") or {}).items():
            sym = norm_sym(raw, cfg)
            if sym not in cfg["symbols"]:
                continue
            for r in rows:
                b = dict(zip(fields, r))
                if None in (b.get("o"), b.get("h"), b.get("l"), b.get("c"), b.get("t")):
                    continue  # FEED1 previo a o/h/l: solo contexto, sin vela
                b["t"] = int(b["t"] // 1000)
                if b["t"] % BAR:
                    continue
                by[sym][b["t"]] = b
    return {s: [m[k] for k in sorted(m)] for s, m in by.items()}


def collection(cfg):
    """Estado de la recolección por símbolo: filas, cuántas con vela completa, última vela."""
    out = {s: {"rows": 0, "ohlc": 0, "last": None, "files": 0} for s in cfg["symbols"]}
    for path in sorted(glob.glob(os.path.join(ROOT, "tvbars", "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        fields = d.get("fields") or []
        ix = {k: i for i, k in enumerate(fields)}
        for raw, rows in (d.get("symbols") or {}).items():
            sym = norm_sym(raw, cfg)
            if sym not in out or not rows:
                continue
            c = out[sym]
            c["files"] += 1
            c["rows"] += len(rows)
            c["ohlc"] += sum(1 for r in rows if all(r[ix[k]] is not None for k in ("o", "h", "l") if k in ix))
            t = max(r[ix["t"]] for r in rows)
            if not c["last"] or t / 1000 > dt.datetime.fromisoformat(c["last"]).timestamp():
                c["last"] = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).isoformat(timespec="minutes")
    return out


def load_events(cfg):
    kl = defaultdict(list)    # sym -> [(t_sec, regime, align)]
    kl_ev = []                # eventos crudos de TDL KL para el lab de niveles
    labev = {}                  # (strat, sym, date) -> rec
    for path in sorted(glob.glob(os.path.join(ROOT, "events", "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                src = str(e.get("src") or "").lower()
                d = e.get("data") or {}
                sym = norm_sym(e.get("sym") or d.get("ticker"), cfg)
                if src == "tdl_kl":
                    t = num(e.get("t") or d.get("time"))
                    if t:
                        kl[sym].append((int(t // 1000), d.get("regime"), d.get("align")))
                        kl_ev.append((sym, int(t // 1000), e))
                elif src.startswith("lab_") and str(e.get("event")).upper() == "SUMMARY":
                    rec = d.get("rec")
                    if isinstance(rec, str):
                        try:
                            rec = json.loads(rec)
                        except ValueError:
                            rec = None
                    if isinstance(rec, dict) and d.get("date"):
                        labev[(src[4:].upper(), sym, d["date"])] = rec
    for s in kl:
        kl[s].sort()
    return kl, kl_ev, labev


def load_news(dry):
    """Días con noticias USD de impacto alto / medio entre 07:00 y 16:00 ET. live/news.json solo
    trae la semana en curso, así que se acumula en state/lab-news.json."""
    path = os.path.join(ROOT, "state", "lab-news.json")
    try:
        with open(path, encoding="utf-8") as f:
            days = json.load(f)
    except (OSError, ValueError):
        days = {}
    try:
        with open(os.path.join(ROOT, "live", "news.json"), encoding="utf-8") as f:
            ev = (json.load(f).get("news") or {}).get("events") or []
    except (OSError, ValueError):
        ev = []
    rank_ = {"high": 2, "medium": 1}
    for e in ev:
        imp = str(e.get("impact") or "").lower()
        if e.get("currency") != "USD" or imp not in rank_ or not e.get("ts"):
            continue
        t = dt.datetime.fromtimestamp(e["ts"] / 1000, NY)
        if not 7 <= t.hour < 16:
            continue
        k = str(t.date())
        if rank_.get(days.get(k), 0) < rank_[imp]:
            days[k] = imp
    if not dry:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(days.items())), f, indent=0)
            f.write("\n")
    return days


def load_plans(cfg):
    out = {}
    for path in glob.glob(os.path.join(ROOT, "plans", "*-pre-ny.json")) + \
            glob.glob(os.path.join(ROOT, "plans", "crypto", "*-ny.json")):
        try:
            with open(path, encoding="utf-8") as f:
                p = json.load(f)
        except (OSError, ValueError):
            continue
        for raw, ins in (p.get("instruments") or {}).items():
            if isinstance(ins, dict):
                b = ins.get("biasSession") or ins.get("biasDay")
                if b in (None, "NEUTRAL") and ins.get("biasDay"):
                    b = ins["biasDay"]
                out[(norm_sym(raw, cfg), p.get("date"))] = b
    return out


# ================================================================ utilidades

def at(date, hhmm, off=0):
    h, m = map(int, hhmm.split(":"))
    d = date + dt.timedelta(days=off)
    return int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=NY).timestamp())


def idx_range(bars, t0, t1):
    return [i for i, b in enumerate(bars) if t0 <= b["t"] < t1]


def complete(ix, t0, t1, pct=0.8):
    return len(ix) >= (t1 - t0) // BAR * pct


MGMT = ["full"]   # se fija desde config["mgmt"] en main


def sim(bars, start, end_t, d, entry, stop, tgt, mgmt="full"):
    """Recorre desde bars[start]. Devuelve (res, r_bruto, mfe, mae, ambiguo).
    mgmt: full = todo a stop o target · be1 = en +1R el stop pasa a la entrada ·
    half1 = en +1R sale la mitad y el resto sigue con stop en la entrada.
    La gestión se activa al cierre de la vela que toca +1R (el stop nuevo vale desde la
    siguiente: conservador). mfe / mae = excursión a favor / en contra en R hasta la salida
    (la vela del stop no suma a favor). ambiguo = stop y target en la misma vela."""
    R = (entry - stop) * d
    last, mfe, mae, act = entry, 0.0, 0.0, False
    half = mgmt == "half1"
    for b in bars[start:]:
        if b["t"] >= end_t:
            break
        fav = ((b["h"] - entry) if d > 0 else (entry - b["l"])) / R
        adv = ((entry - b["l"]) if d > 0 else (b["h"] - entry)) / R
        st = entry if act else stop
        hit_s = (b["l"] <= st) if d > 0 else (b["h"] >= st)
        hit_t = tgt is not None and ((b["h"] >= tgt) if d > 0 else (b["l"] <= tgt))
        if hit_s:
            if not act:
                return "loss", -1.0, mfe, 1.0, hit_t
            return "be", (0.5 if half else 0.0), mfe, mae, hit_t
        mfe, mae = max(mfe, fav), max(mae, adv)
        if hit_t:
            full = (tgt - entry) * d / R
            return "win", (0.5 + 0.5 * full if half and (act or fav >= 1) else full), mfe, mae, False
        if mgmt != "full" and not act and fav >= 1:
            act = True
        last = b["c"]
    rem = (last - entry) * d / R
    return "eod", (0.5 + 0.5 * rem if half and act else rem), mfe, mae, False


def trade(bars, k, end_t, d, entry, stop, tgt, cost, limit_fill_bar=False):
    """Simula y descuenta costo. Con limit_fill_bar, en la vela k (llenado) solo cuenta el stop.
    Guarda riesgo y recompensa en precio (Rpx, rw) para el control de entrada al azar."""
    R = (entry - stop) * d
    if R <= 0 or (tgt is not None and (tgt - entry) * d <= 0):
        return None
    base = {"Rpx": R, "rw": None if tgt is None else (tgt - entry) * d, "ek": k, "endT": end_t, "cost": cost}
    b = bars[k]
    stopped_on_fill = limit_fill_bar and ((b["l"] <= stop) if d > 0 else (b["h"] >= stop))

    def one(mgmt):
        c = cost * (1.5 if mgmt == "half1" else 1.0) / R   # la salida parcial paga media comisión más
        if stopped_on_fill:
            return {**base, "mgmt": mgmt, "res": "loss", "r": round(-1.0 - c, 3), "mfe": 0.0, "mae": 1.0, "amb": False}
        res, r, mfe, mae, amb = sim(bars, k + 1, end_t, d, entry, stop, tgt, mgmt)
        o = {**base, "mgmt": mgmt, "res": res, "r": round(r - c, 3), "mfe": round(mfe, 2), "mae": round(mae, 2), "amb": amb}
        if amb:
            o["rOpt"] = round((tgt - entry) * d / R - c, 3)
        return o

    out = one("full")
    # gestión solo tiene sentido si el target está más allá de +1R (o es el cierre del día)
    if tgt is None or (tgt - entry) * d / R > 1.0 + 1e-9:
        out["alt"] = {m: one(m) for m in MGMT if m != "full"}
    return out


def control(bars, rth, rec, key):
    """Misma fecha, mismo riesgo y recompensa en precio, pero vela y dirección al azar
    (semilla fija por operación, reproducible). Devuelve el R neto del control."""
    rnd = random.Random(zlib.crc32(key.encode()))
    cand = rth[:-1]
    if not cand:
        return None
    j = rnd.choice(cand)
    d = rnd.choice((1, -1))
    entry = bars[j]["c"]
    stop = entry - rec["Rpx"] * d
    tgt = None if rec["rw"] is None else entry + rec["rw"] * d
    m = rec.get("mgmt", "full")
    _, r, _, _, _ = sim(bars, j + 1, rec["endT"], d, entry, stop, tgt, m)
    return round(r - rec["cost"] * (1.5 if m == "half1" else 1.0) / rec["Rpx"], 3)


def target_px(spec, entry, stop, d, edge=None, rng=None):
    R = (entry - stop) * d
    if spec in ("eod", "hold"):
        return None
    if spec.endswith("R"):
        return entry + float(spec[:-1]) * R * d
    if spec.startswith("ext"):
        return edge + float(spec[3:]) * rng * d
    raise ValueError(spec)


# ================================================================ confluencias

def fav(x, d):
    if x is None:
        return None
    return "favor" if x * d > 0 else "contra" if x * d < 0 else "flat"


def features(b, d, sym, date, t_open, ctx):
    c = b["c"]
    g = lambda k: num(b.get(k))
    f = {}
    f["vwap"] = fav(c - g("vwap"), d) if g("vwap") else None
    e20, e50 = g("ema20"), g("ema50")
    if e20 and e50:
        a, s = fav(c - e20, d), fav(e20 - e50, d)
        f["ema"] = a if a == s else "mixed"
    f["ema200"] = fav(c - g("ema200"), d) if g("ema200") else None
    h20, h50 = g("ema20h"), g("ema50h")
    if h20 and h50:
        a, s = fav(c - h50, d), fav(h20 - h50, d)
        f["htf"] = a if a == s else "mixed"
    reg, aln = ctx["kl"](sym, b["t"])
    if reg:
        f["klRegime"] = ("favor" if (reg == "TREND_UP") == (d > 0) else "contra") if reg.startswith("TREND") else reg.lower()
    if aln:
        f["klAlign"] = ("favor" if aln.endswith("UP") == (d > 0) else "contra") if aln.endswith(("UP", "DOWN")) else aln.lower()
    p = ctx["plans"].get((sym, date))
    if p in ("LONG", "SHORT"):
        f["plan"] = "favor" if (p == "LONG") == (d > 0) else "contra"
    elif p:
        f["plan"] = "neutral"
    ch = g("chopIdx")
    if ch is not None:
        f["chop"] = "chop" if ch >= 61.8 else "trend" if ch <= 38.2 else "mid"
    st = g("stretchAtr")
    if st is not None:
        f["stretch"] = "low" if abs(st) < 1 else "mid" if abs(st) < 3 else "high"
    dp = g("dPos")
    if dp is not None:
        f["zone"] = "mid" if 0.25 <= dp <= 0.75 else ("favor" if (dp < 0.25) == (d > 0) else "contra")
    sm = b.get("smt")
    if sm in ("bull", "bear"):
        f["smt"] = "favor" if (sm == "bull") == (d > 0) else "contra"
    elif sm:
        f["smt"] = "none"
    o930, pdc = ctx["dayOpen"], g("pdc")
    if o930 is not None and pdc:
        gap = o930 - pdc
        f["gap"] = "none" if abs(gap) < pdc * 0.0005 else fav(gap, d)
    pdh, pdl = g("pdh"), g("pdl")
    if pdh and pdl and pdc and pdh > pdl:
        cp = (pdc - pdl) / (pdh - pdl)
        f["pdClose"] = "mid" if 0.33 <= cp <= 0.66 else ("favor" if (cp > 0.66) == (d > 0) else "contra")
    f["news"] = ctx["news"].get(str(date), "none")
    mins = (b["t"] - t_open) // 60
    f["time"] = "0-30" if mins < 30 else "30-60" if mins < 60 else "60-120" if mins < 120 else "120+"
    f["dow"] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][date.weekday()]
    return {k: v for k, v in f.items() if v is not None}


# ================================================================ familias

def fam_breakout(fam, bars, sess, rng_ix, cfgx, cost, mk, day_rep, key):
    """ORB / IBB: rango = bars[rng_ix], sesión = índices sess. mk(k, d) -> feats."""
    hi = max(bars[i]["h"] for i in rng_ix)
    lo = min(bars[i]["l"] for i in rng_ix)
    rng = hi - lo
    if rng <= 0:
        return []
    end_t = bars[sess[-1]]["t"] + BAR
    k = next((i for i in sess if bars[i]["c"] > hi or bars[i]["c"] < lo), None)
    rep = {"range": round(rng, 6), "first": "NONE", "failed": False}
    day_rep[key] = rep
    if k is None:
        return []
    d = 1 if bars[k]["c"] > hi else -1
    edge, opp = (hi, lo) if d > 0 else (lo, hi)
    rep["first"] = "UP" if d > 0 else "DOWN"
    rep["failed"] = any((bars[i]["c"] < lo) if d > 0 else (bars[i]["c"] > hi) for i in sess if i >= k)
    feats = mk(k, d)
    atrD = num(bars[k].get("atrD"))
    if atrD:
        feats["#rangeAtr"] = rng / atrD          # numérico: se pasa a terciles por familia
    if fam == "IBB":
        vah, val = num(bars[k].get("vah")), num(bars[k].get("val"))
        if vah and val:
            feats["ibVsVA"] = "inside" if hi <= vah and lo >= val else "outside" if lo > vah or hi < val else "overlap"
    out = []
    for ent in cfgx["entries"]:
        if ent == "close":
            ek, entry, lim = k, bars[k]["c"], False
        else:
            ek = next((i for i in sess if k < i <= k + cfgx.get("retestBars", 6)
                       and ((bars[i]["l"] <= edge) if d > 0 else (bars[i]["h"] >= edge))), None)
            entry, lim = edge, True
        for st in cfgx["stops"]:
            stop = opp if st == "opp" else (hi + lo) / 2 if st == "mid" else edge - 0.25 * rng * d
            for tg in cfgx["targets"]:
                var = f"{key}|{ent}|{st}|{tg}"
                if ek is None:
                    out.append({"fam": fam, "var": var, "dir": d, "res": "nofill", "feat": feats})
                    continue
                t = trade(bars, ek, end_t, d, entry, stop, target_px(tg, entry, stop, d, edge, rng), cost, lim)
                if t:
                    out.append({"fam": fam, "var": var, "dir": d, **t, "feat": feats})
    return out


def fam_ib_levels(bars, sess, ib_ix, cfg, cost, mk, day_rep, prev_close_ix):
    c = cfg["ib"]
    hi = max(bars[i]["h"] for i in ib_ix)
    lo = min(bars[i]["l"] for i in ib_ix)
    rng = hi - lo
    if rng <= 0:
        return []
    end_t = bars[sess[-1]]["t"] + BAR
    out = []
    for pct in c["levels"] + c["controlLevels"]:
        ctrl = pct in c["controlLevels"]
        P = lo + pct / 100 * rng
        j = next((i for i in sess if bars[i]["l"] <= P <= bars[i]["h"]), None)
        name = f"IB{pct:g}"
        rep = day_rep.setdefault("ibLevels", {})
        if j is None:
            rep[name] = "untouched"
            continue
        pc = bars[j - 1]["c"] if j - 1 >= 0 else None
        if pc is None or pc == P:
            continue
        d = 1 if pc > P else -1      # llega desde arriba → soporte → largo
        res = "none"
        for i in [x for x in sess if x >= j]:
            b = bars[i]
            if (b["c"] < P - c["throughClose"] * rng) if d > 0 else (b["c"] > P + c["throughClose"] * rng):
                res = "through"
                break
            if (b["h"] >= P + c["respectMove"] * rng) if d > 0 else (b["l"] <= P - c["respectMove"] * rng):
                res = "respect"
                break
        rep[name] = res
        feats = mk(j, d)
        atrD = num(bars[j].get("atrD"))
        if atrD:
            feats["#rangeAtr"] = rng / atrD
        out.append({"fam": "IBR", "var": name, "ctrl": ctrl, "dir": d, "res": res, "feat": feats})
        for s in c["levelStops"]:
            stop = P - s * rng * d
            for tg in c["levelTargets"]:
                tp = P + 0.25 * rng * d if tg == "next" else target_px(tg, P, stop, d)
                t = trade(bars, j, end_t, d, P, stop, tp, cost, True)
                if t:
                    out.append({"fam": "IBL", "var": f"{name}|s{s:g}|{tg}", "ctrl": ctrl, "dir": d, **t, "feat": feats})
    return out


SWEEP_PAIR = {"asH": "asL", "asL": "asH", "loH": "loL", "loL": "loH", "onh": "onl", "onl": "onh", "pdh": "pdl", "pdl": "pdh"}


def fam_sweep(bars, sess, pre_b, date, t_open, cfg, cost, mk, day_rep):
    c = cfg["sweep"]
    end_t = bars[sess[-1]]["t"] + BAR
    out = []
    rep = day_rep.setdefault("sweep", {})
    ends = {"asH": at(date, "03:00"), "asL": at(date, "03:00"), "pdh": at(date, "18:00", -1), "pdl": at(date, "18:00", -1)}
    for name in c["levels"]:
        L, other = num(pre_b.get(name)), num(pre_b.get(SWEEP_PAIR[name]))
        if L is None:
            continue
        up = name in ("asH", "loH", "onh", "pdh")
        t_end = ends.get(name, t_open)
        pre = any(((b["h"] > L) if up else (b["l"] < L)) for b in bars if t_end <= b["t"] < t_open)
        k = next((i for i in sess if ((bars[i]["h"] > L) if up else (bars[i]["l"] < L))), None)
        rep[name] = {"preNY": pre, "swept": k is not None}
        if k is None:
            continue
        atr = num(bars[k].get("atr5")) or num(pre_b.get("atr5"))
        # --- reversa: reclaim en reclaimBars velas desde la barrida
        rk = next((i for i in sess if k <= i < k + c["reclaimBars"]
                   and ((bars[i]["c"] < L) if up else (bars[i]["c"] > L))), None)
        rep[name]["reclaim"] = rk is not None
        if rk is not None:
            d = -1 if up else 1
            ext = max(bars[i]["h"] for i in range(k, rk + 1)) if up else min(bars[i]["l"] for i in range(k, rk + 1))
            feats = {**mk(rk, d), "preNY": "yes" if pre else "no"}
            if atr:
                feats["#depth"] = abs(ext - L) / atr   # cuánto barrió, en ATR5
            entry = bars[rk]["c"]
            for st in c["revStops"]:
                if st == "extreme+atr" and not atr:
                    continue
                stop = ext + (0.25 * atr if st == "extreme+atr" else 0) * (-d)
                for tg in c["revTargets"]:
                    tp = other if tg == "range" else target_px(tg, entry, stop, d)
                    if tg == "range" and other is None:
                        continue
                    t = trade(bars, rk, end_t, d, entry, stop, tp, cost)
                    if t:
                        out.append({"fam": "SWR", "var": f"{name}|{st}|{tg}", "dir": d, **t, "feat": feats})
        # --- continuación: N cierres seguidos fuera
        if atr:
            n, ck = 0, None
            for i in [x for x in sess if x >= k]:
                n = n + 1 if ((bars[i]["c"] > L) if up else (bars[i]["c"] < L)) else 0
                if n >= c["contCloses"]:
                    ck = i
                    break
            if ck is not None:
                d = 1 if up else -1
                entry, stop = bars[ck]["c"], L - atr * d
                feats = {**mk(ck, d), "preNY": "yes" if pre else "no"}
                for tg in c["contTargets"]:
                    t = trade(bars, ck, end_t, d, entry, stop, target_px(tg, entry, stop, d), cost)
                    if t:
                        out.append({"fam": "SWC", "var": f"{name}|{tg}", "dir": d, **t, "feat": feats})
    return out


def fam_va80(bars, rth, pre_b, cfg, cost, mk, day_rep):
    """Regla del 80 %: abre fuera del value area de ayer y vuelve a entrar con N cierres
    seguidos dentro → hacia el otro lado. Control: % de días que recorren todo el VA igual."""
    c = cfg["va80"]
    vah, val, poc = num(pre_b.get("vah")), num(pre_b.get("val")), num(pre_b.get("poc"))
    if None in (vah, val) or vah <= val:
        return []
    poc = poc if poc is not None and val < poc < vah else (vah + val) / 2
    end_t = bars[rth[-1]]["t"] + BAR
    o = bars[rth[0]]["o"]
    side = "above" if o > vah else "below" if o < val else "inside"
    both = any(bars[i]["h"] >= vah for i in rth) and any(bars[i]["l"] <= val for i in rth)
    rep = {"open": side, "touchedBoth": both}
    day_rep["va80"] = rep
    if side == "inside":
        return []
    d = -1 if side == "above" else 1
    edge, far = (vah, val) if d < 0 else (val, vah)
    n, k = 0, None
    for i in rth:
        n = n + 1 if val <= bars[i]["c"] <= vah else 0
        if n >= c["closesInside"]:
            k = i
            break
    rep["reentry"] = k is not None
    if k is None:
        return []
    after = [i for i in rth if i > k]
    rep["reachedPoc"] = any(((bars[i]["l"] <= poc) if d < 0 else (bars[i]["h"] >= poc)) for i in after)
    rep["reachedFar"] = any(((bars[i]["l"] <= far) if d < 0 else (bars[i]["h"] >= far)) for i in after)
    atr = num(bars[k].get("atr5")) or num(pre_b.get("atr5"))
    sess_ext = (max if d < 0 else min)(bars[i]["h"] if d < 0 else bars[i]["l"] for i in rth if i <= k)
    feats = {**mk(k, d), "open": side}
    atrD = num(bars[k].get("atrD")) or num(pre_b.get("atrD"))
    if atrD:
        feats["#openDist"] = abs(o - edge) / atrD
        feats["#vaWidth"] = (vah - val) / atrD
    out = []
    for ent in c["entries"]:
        if ent == "close":
            ek, entry, lim = k, bars[k]["c"], False
        else:
            ek = next((i for i in after if i <= k + c["retestBars"]
                       and ((bars[i]["h"] >= edge) if d < 0 else (bars[i]["l"] <= edge))), None)
            entry, lim = edge, True
        for st in c["stops"]:
            if st == "edge" and not atr:
                continue
            stop = edge - 0.25 * atr * d if st == "edge" else sess_ext
            for tg in c["targets"]:
                var = f"{ent}|{st}|{tg}"
                if ek is None:
                    out.append({"fam": "VA80", "var": var, "dir": d, "res": "nofill", "feat": feats})
                    continue
                tp = poc if tg == "poc" else far if tg == "far" else target_px(tg, entry, stop, d)
                t = trade(bars, ek, end_t, d, entry, stop, tp, cost, lim)
                if t:
                    out.append({"fam": "VA80", "var": var, "dir": d, **t, "feat": feats})
    return out


def fam_pullback(bars, rth, cfg, cost, mk):
    """Retroceso a EMA20 / VWAP: el precio venía del mismo lado (minAway ATR5 de separación) y la
    vela toca la referencia de la vela anterior (sin mirar al futuro). La dirección la da el lado
    de llegada; la tendencia (htf, klRegime...) queda como confluencia, así 'contra' es el control."""
    c = cfg["pullback"]
    end_t = bars[rth[-1]]["t"] + BAR
    out = []
    for ref in c["refs"]:
        side, away, taken = 0, False, 0
        for i in rth:
            if i == 0 or taken >= c["maxPerDay"]:
                continue
            lvl = num(bars[i - 1].get(ref))
            atr = num(bars[i - 1].get("atr5"))
            b = bars[i]
            if lvl is None or not atr:
                continue
            pc = bars[i - 1]["c"]
            s = 1 if pc > lvl else -1 if pc < lvl else 0
            if s != side:
                side, away = s, False
            if side and (pc - lvl) * side >= c["minAway"] * atr:
                away = True
            touch = side and away and ((b["l"] <= lvl) if side > 0 else (b["h"] >= lvl))
            if not touch:
                continue
            d = side
            taken += 1
            away = False
            feats = mk(i - 1, d)   # contexto de la vela previa al toque: el límite se pone antes
            feats["nth"] = str(taken)
            e20, e50 = num(bars[i - 1].get("ema20")), num(bars[i - 1].get("ema50"))
            if e20 and e50:
                feats["#trendStr"] = abs(e20 - e50) / atr
            prior = [j for j in rth if j < i]
            hod = (max(bars[j]["h"] for j in prior) if d > 0 else min(bars[j]["l"] for j in prior)) if prior else None
            # confirmación: cierre de vuelta del lado de llegada en la vela del toque o la siguiente
            ck = next((j for j in (i, i + 1) if j in rth and ((bars[j]["c"] > lvl) if d > 0 else (bars[j]["c"] < lvl))), None)
            for ent in c["entries"]:
                if ent == "limit":
                    ek, entry, lim = i, lvl, True
                else:
                    ek, entry, lim = ck, (bars[ck]["c"] if ck is not None else None), False
                for st in c["stops"]:
                    for tg in c["targets"]:
                        var = f"{ref}|{ent}|{st}|{tg}"
                        if ek is None:
                            out.append({"fam": "PB", "var": var, "dir": d, "res": "nofill", "feat": feats})
                            continue
                        if st == "swing":
                            if ent == "limit":
                                continue   # el mínimo del toque aún no existe al poner el límite
                            stop = (min if d > 0 else max)(bars[j]["l"] if d > 0 else bars[j]["h"] for j in range(i, ek + 1))
                        else:
                            stop = entry - 0.5 * atr * d
                        if tg == "hod" and hod is None:
                            continue
                        tp = hod if tg == "hod" else target_px(tg, entry, stop, d)
                        t = trade(bars, ek, end_t, d, entry, stop, tp, cost, lim)
                        if t:
                            out.append({"fam": "PB", "var": var, "dir": d, **t, "feat": feats})
    return out


def zone_entry_table(lab):
    """Zonas: las tres formas de entrar con la misma salida (límite honesto vs gatillo)."""
    z = lab.get("ZON")
    if not z:
        return None
    by = {v["var"]: v for v in z["variants"]}
    rows = []
    for tg in ("tp1", "tp1|half1", "tp1|be1", "1R", "2R", "hold"):
        row = {"exit": tg}
        for kind in ("limit", "trigger", "trigRt"):
            v = by.get(f"{kind}|{tg}")
            if v:
                row[kind] = {k: v.get(k) for k in ("n", "expR", "winPct", "fillPct", "edgeVsCtrl", "lb")}
        if len(row) > 1:
            rows.append(row)
    return rows


def vs_rbo(lab):
    """Mejor variante del setup frente a la mejor ruptura simple, con el mismo stop y target."""
    a, b = lab.get("RIF"), lab.get("RBO")
    if not a or not b:
        return None
    rb = {v["var"].split("|", 1)[1]: v for v in b["variants"] if "|" in v["var"]}
    out = []
    for v in a["variants"][:10]:
        tail = v["var"].split("|", 1)[1]
        if tail in rb:
            o = rb[tail]
            out.append({"var": v["var"], "rif": {k: v.get(k) for k in ("n", "expR")},
                        "rbo": {"var": o["var"], **{k: o.get(k) for k in ("n", "expR")}},
                        "diffR": round((v.get("expR") or 0) - (o.get("expR") or 0), 3)})
    return out


def trend_split(recs, minN):
    """Pullback: cada variante con la tendencia 1h a favor frente a en contra (el control)."""
    by = defaultdict(lambda: {"favor": [], "contra": []})
    for r in recs:
        h = r["feat"].get("htf")
        if h in ("favor", "contra"):
            by[r["var"]][h].append(r)
    out = []
    for v, g in by.items():
        a, b = stats(g["favor"]), stats(g["contra"])
        if a["n"] >= minN and b["n"] >= minN:
            out.append({"var": v, "favor": {k: a.get(k) for k in ("n", "expR", "winPct")},
                        "contra": {k: b.get(k) for k in ("n", "expR", "winPct")},
                        "diffR": round(a["expR"] - b["expR"], 3)})
    return sorted(out, key=lambda x: -x["diffR"])[:20]


# ================================================================ rango + iFVG (setup de TDL PA)

def atr_series(bars, n):
    """ta.atr de Pine: RMA del true range, sembrada con la media de las primeras n velas."""
    out, a, prev, acc = [None] * len(bars), None, None, []
    for i, b in enumerate(bars):
        tr = b["h"] - b["l"] if prev is None else max(b["h"] - b["l"], abs(b["h"] - prev), abs(b["l"] - prev))
        prev = b["c"]
        if a is None:
            acc.append(tr)
            if len(acc) == n:
                a = sum(acc) / n
        else:
            a = (a * (n - 1) + tr) / n
        out[i] = a
    return out


def ses_of(t):
    x = dt.datetime.fromtimestamp(t, NY)
    m = x.hour * 60 + x.minute
    return "asia" if m >= 1080 or m < 180 else "london" if m < 570 else "ny" if m < 960 else "close"


def ranges_tdl_pa(bars, crypto, c):
    """Rangos como TDL PA en 5m: ventana de rangeBars velas con alto - bajo ≤ mult × ATR(100);
    ruptura = cierre fuera ± buf × ATR(14); fakeout = vuelve a cerrar dentro antes de fakeBars velas
    (el rango sigue vivo); sweeps = mecha fuera ≥ 40 % de la vela y cierre dentro; en futuros el rango
    muere al empezar el día (18:00 NY). Devuelve las rupturas con los datos del rango."""
    L, a14, a100 = c["rangeBars"], atr_series(bars, 14), atr_series(bars, 100)
    events, state, r_end, top = [], 0, -1, None
    fake_bar, fake_dir, sw_last = -1000, 0, -1000
    for i, b in enumerate(bars):
        new_day = False
        if i > 0 and not crypto:
            anc = at(dt.datetime.fromtimestamp(b["t"], NY).date(), "18:00")
            if anc > b["t"]:
                anc -= 86400
            new_day = bars[i - 1]["t"] < anc <= b["t"]
        if new_day and state == 1:
            state, r_end = 0, i
        if a14[i] is None or a100[i] is None or i < L - 1:
            continue
        buf = c["boBuf"] * a14[i]
        if state == 0:
            hh = max(x["h"] for x in bars[i - L + 1:i + 1])
            ll = min(x["l"] for x in bars[i - L + 1:i + 1])
            if hh - ll <= c["rangeMult"] * a100[i] and i - L + 1 > r_end:
                top, bot, start, sw_up, sw_dn, state = hh, ll, i - L + 1, 0, 0, 1
        elif state == 1:
            rng = b["h"] - b["l"]
            if b["c"] > top + buf or b["c"] < bot - buf:
                d = 1 if b["c"] > top else -1
                events.append({"bo": i, "dir": d, "top": top, "bot": bot, "start": start,
                               "swOpp": sw_dn if d > 0 else sw_up,
                               "fakeBefore": fake_dir == d and i - fake_bar <= 10})
                state, bo, r_end = 2 * d, i, i
            elif b["h"] > top and b["c"] <= top and i - sw_last > 2 and (b["h"] - max(b["o"], b["c"])) >= 0.4 * rng:
                sw_up, sw_last = sw_up + 1, i
            elif b["l"] < bot and b["c"] >= bot and i - sw_last > 2 and (min(b["o"], b["c"]) - b["l"]) >= 0.4 * rng:
                sw_dn, sw_last = sw_dn + 1, i
            elif i - start > c["maxBars"]:
                state, r_end = 0, i
        elif state == 2:
            if b["c"] < top:
                fake_bar, fake_dir, state = i, 1, 1
            elif i - bo >= c["fakeBars"]:
                state = 0
        elif state == -2:
            if b["c"] > bot:
                fake_bar, fake_dir, state = i, -1, 1
            elif i - bo >= c["fakeBars"]:
                state = 0
    return events, a14


def fvgs_tdl_pa(bars, a14, c):
    """FVG como TDL PA (hueco ≥ minSize × ATR14) con la vela en que se invierte por cierre."""
    out = []
    for i in range(2, len(bars)):
        if a14[i] is None:
            continue
        b, b2 = bars[i], bars[i - 2]
        if b["h"] < b2["l"] and b2["l"] - b["h"] >= c["fvgMin"] * a14[i]:      # bajista: hueco arriba
            out.append({"i": i, "dir": -1, "top": b2["l"], "bot": b["h"]})
        elif b["l"] > b2["h"] and b["l"] - b2["h"] >= c["fvgMin"] * a14[i]:    # alcista: hueco abajo
            out.append({"i": i, "dir": 1, "top": b["l"], "bot": b2["h"]})
    for f in out:
        f["inv"] = next((j for j in range(f["i"] + 1, min(len(bars), f["i"] + c["fvgMaxAge"]))
                         if ((bars[j]["c"] > f["top"]) if f["dir"] < 0 else (bars[j]["c"] < f["bot"]))), None)
    return out


def end_of_hold(t, crypto, hours):
    e = t + hours * 3600
    if not crypto:
        x = dt.datetime.fromtimestamp(t, NY)
        close = at(x.date(), "17:00")
        if close <= t:
            close += 86400
        e = min(e, close)
    return e


def fam_range_ifvg(bars, sym, crypto, cfg, cost, ctx_for):
    """RIF: rango → ruptura → cierre que invierte un FVG en contra que estaba antes de la ruptura.
    RBO: la misma ruptura sola (comparación: ¿la inversión del FVG aporta?)."""
    c = cfg["rangeIfvg"]
    events, a14 = ranges_tdl_pa(bars, crypto, c)
    fv = fvgs_tdl_pa(bars, a14, c)
    used, out, summ = set(), [], {"breaks": 0, "withInversion": 0}
    by_inv = defaultdict(list)
    for f in fv:
        if f["inv"] is not None:
            by_inv[f["inv"]].append(f)

    def lim_fill(level, d, i0, n):
        return next((j for j in range(i0 + 1, min(len(bars), i0 + 1 + n))
                     if ((bars[j]["l"] <= level) if d > 0 else (bars[j]["h"] >= level))), None)

    def stop_for(st, d, ev, f, k_lo, k_hi, atr):
        if st == "rangeOpp":
            return (ev["bot"] - 0.1 * atr) if d > 0 else (ev["top"] + 0.1 * atr)
        if st == "rangeMid":
            return (ev["top"] + ev["bot"]) / 2
        if st == "ifvgFar":
            return None if f is None else ((f["bot"] - 0.1 * atr) if d > 0 else (f["top"] + 0.1 * atr))
        if st == "swing":
            seg = bars[k_lo:k_hi + 1]
            return (min(x["l"] for x in seg) - 0.1 * atr) if d > 0 else (max(x["h"] for x in seg) + 0.1 * atr)

    def run(fam, ev, f, sig, entries, d, base_feats):
        atr = a14[sig] or 0
        if not atr:
            return
        edge = ev["top"] if d > 0 else ev["bot"]
        mm = edge + (ev["top"] - ev["bot"]) * d
        lvl = {"close": None, "rangeRt": edge}
        if f is not None:
            lvl["ifvg"] = f["top"] if d > 0 else f["bot"]
            lvl["ce"] = (f["top"] + f["bot"]) / 2
        for ent in entries:
            if ent == "close":
                ek, entry, lim = sig, bars[sig]["c"], False
            else:
                L = lvl.get(ent)
                if L is None:
                    continue
                ek, entry, lim = lim_fill(L, d, sig, c["retestBars"][ent]), L, True
            for st in c["stops"][fam]:
                for tg in c["targets"]:
                    var = f"{ent}|{st}|{tg}"
                    if ek is None:
                        out.append({"fam": fam, "var": var, "dir": d, "res": "nofill", "feat": base_feats,
                                    "sym": sym, "date": str(dt.datetime.fromtimestamp(bars[sig]["t"], NY).date())})
                        continue
                    stop = stop_for(st, d, ev, f, ev["bo"], sig, atr)
                    if stop is None:
                        continue
                    tp = mm if tg == "mm" else target_px(tg, entry, stop, d)
                    end_t = end_of_hold(bars[ek]["t"], crypto, c["maxHoldHours"])
                    t = trade(bars, ek, end_t, d, entry, stop, tp, cost, lim)
                    if t:
                        date = str(dt.datetime.fromtimestamp(bars[ek]["t"], NY).date())
                        out.append({"fam": fam, "var": var, "dir": d, **t, "feat": base_feats, "sym": sym, "date": date})

    for ev in events:
        d, bo = ev["dir"], ev["bo"]
        summ["breaks"] += 1
        pre0 = ev["start"] - 1
        prior = None
        if pre0 - c["priorBars"] >= 0 and a14[pre0]:
            mv = (bars[pre0]["c"] - bars[pre0 - c["priorBars"]]["c"]) / a14[pre0]
            prior = "flat" if abs(mv) < c["priorAtr"] else ("favor" if mv * d > 0 else "contra")

        def feats(k):
            f = ctx_for(k, d)
            f["time"] = ses_of(bars[k]["t"])
            if prior:
                f["priorTrend"] = prior
            f["sweptOpp"] = "yes" if ev["swOpp"] else "no"
            f["fakeBefore"] = "yes" if ev["fakeBefore"] else "no"
            f["#rangeBars"] = bo - ev["start"]
            if a14[bo]:
                f["#rangeAtr"] = (ev["top"] - ev["bot"]) / a14[bo]
            return f

        run("RBO", ev, None, bo, c["entries"]["RBO"], d, feats(bo))
        # FVG en contra (bajista para un largo) formado antes de la ruptura, sin invertir aún,
        # fuera del rango del lado de la ruptura, invertido dentro de invWindow velas
        cands = [f for j in range(bo, bo + c["invWindow"] + 1) for f in by_inv.get(j, ())
                 if f["dir"] == -d and f["i"] < bo and id(f) not in used
                 and ((f["top"] > ev["top"]) if d > 0 else (f["bot"] < ev["bot"]))]
        if not cands:
            continue
        f = min(cands, key=lambda x: (x["inv"], x["top"] if d > 0 else -x["bot"]))
        inv = f["inv"]
        # si antes de invertir volvió a cerrar dentro del rango, la ruptura falló
        if any(((bars[j]["c"] < ev["top"]) if d > 0 else (bars[j]["c"] > ev["bot"])) for j in range(bo + 1, inv + 1)):
            continue
        used.add(id(f))
        summ["withInversion"] += 1
        bf = feats(inv)
        bf["#boToInv"] = inv - bo
        bf["#fvgAge"] = inv - f["i"]
        run("RIF", ev, f, inv, c["entries"]["RIF"], d, bf)
    return out, summ


# ================================================================ zonas de Mi Mesa (eventos del indicador)

ZONE_KEYS = ["loH", "sh5", "ibh", "pdh", "sh4h", "ema200"]   # las que más separaban en el reporte teórico


def load_zone_events(cfg):
    """Eventos tocada / armada del indicador de zonas de Mi Mesa (session-analyst-bus/zones/events).
    En la GitHub Action se clona en _sa/; ZONES_DIR lo sobrescribe."""
    cands = [os.environ.get("ZONES_DIR"), os.path.join(ROOT, "_sa", "zones", "events"),
             os.path.join(os.path.dirname(ROOT), "session-analyst-bus", "zones", "events"),
             os.path.join(os.path.dirname(ROOT), "jesusreyna2016", "session-analyst-bus", "zones", "events")]
    d = next((c for c in cands if c and os.path.isdir(c)), None)
    out, seen = defaultdict(list), set()
    if not d:
        return out, None
    for path in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("ev") not in ("tocada", "armada"):
                    continue
                sym = norm_sym(e.get("sym"), cfg)
                k = (sym, e["ev"], e.get("id"), e.get("t"))
                if sym not in cfg["symbols"] or k in seen or None in (e.get("entry"), e.get("stop"), e.get("t")):
                    continue
                seen.add(k)
                out[sym].append(e)
    for v in out.values():
        v.sort(key=lambda e: e["t"])
    return out, d


def zone_feats(e, d):
    f = e.get("f") or {}
    out = {"side": "long" if d > 0 else "short", "grade": e.get("grade") or "·"}
    al = str(f.get("al", ""))
    out["zoneBias"] = {"1": "favor", "0": "neutral", "-1": "contra"}.get(al, "·")
    ch, st, rr = num(f.get("chop")), num(f.get("str")), num(f.get("rr"))
    if ch is not None:
        out["zoneChop"] = "<50" if ch < 50 else ">=61.8" if ch >= 61.8 else "50-61.8"
    if st is not None:
        out["stretchVwap"] = "<1" if abs(st) < 1 else ">=2" if abs(st) >= 2 else "1-2"
    if rr is not None:
        out["rrTp1"] = "<1.5" if rr < 1.5 else ">=2.5" if rr >= 2.5 else "1.5-2.5"
    keys = set(str(f.get("keys") or "").split("+"))
    for k in ZONE_KEYS:
        out["k_" + k] = "yes" if k in keys else "no"
    return out


def fam_zones(bars, sym, evs, crypto, cfg, cost, ctx_for):
    """ZON: límite en la entrada de TODA zona tocada (la orden puede estar puesta antes del toque:
    la zona ya está dibujada), sin el filtro de 'armada', que se decide después. Se cancela si la
    zona se resuelve (cierre más allá del stop o del TP1) antes de llenarse. Comparación: entrar al
    cierre del gatillo ('armada') y gatillo + límite si regresa a la entrada."""
    c = cfg["zones"]
    ix = {b["t"]: i for i, b in enumerate(bars)}
    ts = [b["t"] for b in bars]
    out = []
    summ = {"touched": 0, "armed": 0}

    def first_idx(t):
        i = ix.get(t)
        if i is None:
            i = bisect.bisect_left(ts, t)
            i = i if i < len(bars) and bars[i]["t"] - t <= 3600 else None
        return i

    def resolved(b, d, stop, tp1):
        return ((b["c"] < stop) if d > 0 else (b["c"] > stop)) or \
               (tp1 is not None and ((b["c"] >= tp1) if d > 0 else (b["c"] <= tp1)))

    def limit_fill(i0, d, entry, stop, tp1, n):
        for j in range(i0, min(len(bars), i0 + n)):
            b = bars[j]
            if (b["l"] <= entry) if d > 0 else (b["h"] >= entry):
                return j
            if resolved(b, d, stop, tp1):
                return None
        return None

    def emit(kind, e, k, entry, lim, d):
        stop, tp1 = num(e["stop"]), num(e.get("tp1"))
        date = str(dt.datetime.fromtimestamp(bars[k]["t"] if k is not None else e["t"] / 1000, NY).date())
        feats = None
        for tg in c["targets"]:
            var = f"{kind}|{tg}"
            if k is None:
                out.append({"fam": "ZON", "var": var, "dir": d, "res": "nofill", "feat": feats or {}, "sym": sym, "date": date})
                continue
            if feats is None:
                feats = {**ctx_for(k, d), **zone_feats(e, d)}
                feats["time"] = (e.get("f") or {}).get("sess") or ses_of(bars[k]["t"])
            tp = tp1 if tg == "tp1" else target_px(tg, entry, stop, d)
            if tg == "tp1" and (tp1 is None or (tp1 - entry) * d <= 0):
                continue
            end_t = end_of_hold(bars[k]["t"], crypto, c["maxHoldHours"])
            t = trade(bars, k, end_t, d, entry, stop, tp, cost, lim)
            if t:
                out.append({"fam": "ZON", "var": var, "dir": d, **t, "feat": feats, "sym": sym, "date": date})

    for e in evs:
        d = 1 if e.get("side") == "long" else -1
        i0 = first_idx(e["t"] // 1000)
        if i0 is None:
            continue
        entry, stop, tp1 = num(e["entry"]), num(e["stop"]), num(e.get("tp1"))
        if e["ev"] == "tocada":
            summ["touched"] += 1
            emit("limit", e, limit_fill(i0, d, entry, stop, tp1, c["fillBars"]), entry, True, d)
        else:
            summ["armed"] += 1
            # en 5m el indicador marca 'armada' con la hora de apertura de la vela del gatillo
            # (barstate.isconfirmed): se entra a su cierre, no antes
            k = i0
            emit("trigger", e, k, bars[k]["c"], False, d)
            emit("trigRt", e, limit_fill(k + 1, d, entry, stop, tp1, c["fillBars"]) if k + 1 < len(bars) else None, entry, True, d)
    return out, summ


# ================================================================ agregados

def stats(rows):
    fills = [r for r in rows if r["res"] != "nofill"]
    n = len(fills)
    s = {"n": n}
    if len(rows) > n:
        s["fillPct"] = round(100 * n / len(rows), 1)
    if not n:
        return s
    rs = [r["r"] for r in fills]
    m = sum(rs) / n
    # error típico agrupado por día: las operaciones del mismo día (otros símbolos, otras
    # variantes de la misma señal) no son pruebas independientes
    cl = defaultdict(float)
    for r in fills:
        cl[r.get("date")] += r["r"] - m
    G = len(cl)
    se = math.sqrt(G / (G - 1) * sum(v * v for v in cl.values())) / n if G > 1 else None
    gw = sum(x for x in rs if x > 0)
    gl = -sum(x for x in rs if x < 0)
    s.update({"days": G, "winPct": round(100 * sum(x > 0 for x in rs) / n, 1), "expR": round(m, 3),
              "se": round(se, 3) if se is not None else None,
              "lb": round(m - se, 3) if se is not None else round(m - abs(m), 3),
              "pf": round(gw / gl, 2) if gl else None, "sumR": round(sum(rs), 2)})
    cr = [r["cr"] for r in fills if r.get("cr") is not None]
    if cr:
        s["ctrlExpR"] = round(sum(cr) / len(cr), 3)
        s["edgeVsCtrl"] = round(m - s["ctrlExpR"], 3)
    if any("mfe" in r for r in fills):
        mf = sorted(r.get("mfe", 0) for r in fills)
        ma = sorted(r.get("mae", 0) for r in fills)
        q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
        s["mfe"] = {"p50": q(mf, .5), "p75": q(mf, .75)}
        s["mae"] = {"p50": q(ma, .5), "p75": q(ma, .75)}
        amb = [r for r in fills if r.get("amb")]
        if amb:
            s["ambPct"] = round(100 * len(amb) / n, 1)
            s["expROpt"] = round(sum(r.get("rOpt", r["r"]) for r in fills) / n, 3)
    if se is not None and m > 0:
        need = math.ceil((1.96 * se * math.sqrt(n) / m) ** 2)
        s["nMore95"] = max(0, need - n)   # operaciones que faltan para que lb95 > 0 si se mantiene
    return s


def respect_stats(rows):
    n = len(rows)
    rs = sum(r["res"] == "respect" for r in rows)
    th = sum(r["res"] == "through" for r in rows)
    dec = rs + th
    return {"n": n, "respectPct": round(100 * rs / dec, 1) if dec else None,
            "throughPct": round(100 * th / dec, 1) if dec else None,
            "undecidedPct": round(100 * (n - dec) / n, 1) if n else None}


COMBO_TOP, COMBO_BOTTOM = 15, 5


def rank(recs, minN, comboN):
    by_var = defaultdict(list)
    for r in recs:
        by_var[r["var"]].append(r)
    variants = []
    for v, rows in by_var.items():
        s = stats(rows)
        s["var"] = v
        s["ctrl"] = bool(rows[0].get("ctrl"))
        variants.append(s)
    variants.sort(key=lambda s: (s["n"] >= minN, s.get("lb") if s.get("lb") is not None else -9), reverse=True)
    # combinaciones solo sobre las mejores y las peores variantes con muestra: menos
    # comparaciones (menos "ganadores" por suerte) y tiempo acotado
    ok = [s["var"] for s in variants if s["n"] >= comboN]
    pick = ok[:COMBO_TOP] + [v for v in ok[-COMBO_BOTTOM:] if v not in ok[:COMBO_TOP]]
    combos = []
    for v in pick:
        fills = [r for r in by_var[v] if r["res"] != "nofill"]
        keys = sorted({k for r in fills for k in r["feat"]})
        for i, f1 in enumerate(keys):
            for val in {r["feat"].get(f1) for r in fills} - {None}:
                sub = [r for r in fills if r["feat"].get(f1) == val]
                if len(sub) < comboN:
                    continue
                combos.append({"var": v, "when": {f1: val}, **stats(sub)})
                for f2 in keys[i + 1:]:
                    for val2 in {r["feat"].get(f2) for r in sub} - {None}:
                        sub2 = [r for r in sub if r["feat"].get(f2) == val2]
                        if len(sub2) >= comboN:
                            combos.append({"var": v, "when": {f1: val, f2: val2}, **stats(sub2)})
    combos.sort(key=lambda s: s.get("lb") if s.get("lb") is not None else -9, reverse=True)
    return {"variants": variants[:40], "best": combos[:20], "worst": combos[::-1][:10], "nVariants": len(variants)}


def match(r, when):
    return all(r["feat"].get(k) == v for k, v in when.items())


def walk_forward(recs, minN, comboN, frac, min_days):
    """Elige con los días viejos (in-sample) y mide en los nuevos (out-of-sample)."""
    dates = sorted({r["date"] for r in recs})
    if len(dates) < min_days:
        return {"skipped": f"faltan dias ({len(dates)} de {min_days})"}
    cut = dates[int(len(dates) * frac)]
    ins = [r for r in recs if r["date"] < cut]
    oos = [r for r in recs if r["date"] >= cut]
    rk = rank(ins, minN, comboN)
    pick = lambda s: {k: s.get(k) for k in ("n", "days", "expR", "lb")}
    vs = []
    for v in [x for x in rk["variants"] if x["n"] >= minN][:10]:
        o = stats([r for r in oos if r["var"] == v["var"]])
        vs.append({"var": v["var"], "in": pick(v), "out": pick(o), "holds": (o.get("expR") or 0) > 0})
    cs = []
    for c in rk["best"][:10]:
        o = stats([r for r in oos if r["var"] == c["var"] and match(r, c["when"]) and r["res"] != "nofill"])
        cs.append({"var": c["var"], "when": c["when"], "in": pick(c), "out": pick(o), "holds": (o.get("expR") or 0) > 0})
    return {"splitAt": cut, "inDays": len({r["date"] for r in ins}), "outDays": len({r["date"] for r in oos}),
            "variants": vs, "combos": cs,
            "survivors": [x["var"] for x in vs if x["holds"]] + [f'{x["var"]} {x["when"]}' for x in cs if x["holds"]]}


def bucketize(recs):
    """Confluencias numéricas (#clave) → low / mid / high por terciles de la familia."""
    keys = {k for r in recs for k in r["feat"] if k.startswith("#")}
    for k in keys:
        vals = sorted(r["feat"][k] for r in recs if k in r["feat"])
        if len(vals) < 3:
            continue
        a, b = vals[len(vals) // 3], vals[2 * len(vals) // 3]
        name = k[1:]
        for r in recs:
            if k in r["feat"]:
                x = r["feat"].pop(k)
                r["feat"][name] = "low" if x < a else "high" if x > b else "mid"
    return recs


def feature_effect(recs, minN):
    """Para la familia: expR por valor de cada confluencia, sobre todas sus variantes."""
    out = {}
    fills = [r for r in recs if r["res"] != "nofill" and "r" in r]
    for f in sorted({k for r in fills for k in r["feat"]}):
        vals = defaultdict(list)
        for r in fills:
            if f in r["feat"]:
                vals[r["feat"][f]].append(r)
        if vals:
            out[f] = {v: {k: s[k] for k in ("n", "expR", "winPct") if k in s}
                      for v, rows in sorted(vals.items()) for s in [stats(rows)] if s["n"] >= minN}
    return {k: v for k, v in out.items() if v}


# ================================================================ lab de niveles TDL KL (histórico propio)

HOLD = {"REJECT", "SWEEP", "RETEST"}
BREAK = {"ACCEPT_UP", "ACCEPT_DOWN", "FAILED_BREAK", "CROSS"}


def kl_lab(kl_ev, minN):
    """Toque de un nivel → primer desenlace del mismo nivel en 60 min (definición de TDL KL:
    aguanta = rechazo / sweep / retest; rompe = aceptado / ruptura fallida / cruce)."""
    seq = defaultdict(list)
    for sym, t, e in kl_ev:
        if e.get("kind") in ("CISD", "ALIGN", None):
            continue
        seq[(sym, e.get("kind"), str((e.get("data") or {}).get("tf")))].append((t, e))
    recs = []
    for (sym, kind, tf), evs in seq.items():
        evs.sort(key=lambda x: x[0])
        for i, (t, e) in enumerate(evs):
            if e.get("event") != "TOUCH":
                continue
            out = next((x for tt, x in evs[i + 1:] if tt - t <= 3600 and x.get("event") in HOLD | BREAK), None)
            d = e.get("data") or {}
            dist = num(d.get("dist"))
            role = None if dist is None or dist == 0 else ("support" if dist > 0 else "resistance")
            def rel(x):
                if not x or not role or not x.endswith(("UP", "DOWN")):
                    return (x or "none").lower()
                return "favor" if x.endswith("UP") == (role == "support") else "contra"
            recs.append({"sym": sym, "kind": kind, "res": "hold" if out and out["event"] in HOLD
                         else "break" if out else "none", "role": role, "regime": rel(d.get("regime")),
                         "align": rel(d.get("align")), "session": d.get("session")})
    def s(rows):
        h = sum(r["res"] == "hold" for r in rows)
        b = sum(r["res"] == "break" for r in rows)
        return {"n": len(rows), "holdPct": round(100 * h / (h + b), 1) if h + b else None,
                "decidedPct": round(100 * (h + b) / len(rows), 1) if rows else None}
    by_kind = defaultdict(list)
    for r in recs:
        by_kind[r["kind"]].append(r)
    kinds = {k: s(v) for k, v in by_kind.items() if len(v) >= minN}
    ctx = {}
    for f in ("role", "regime", "align", "session"):
        g = defaultdict(list)
        for r in recs:
            g[r[f]].append(r)
        ctx[f] = {str(k): s(v) for k, v in g.items() if len(v) >= minN}
    return {"touches": len(recs), "all": s(recs) if recs else None,
            "byLevel": dict(sorted(kinds.items(), key=lambda kv: -(kv[1]["holdPct"] or 0))), "byContext": ctx,
            "note": "Desenlace segun los eventos de TDL KL. En la medicion de nov-11 los niveles clave no aguantaron mas que niveles de control: comparar contra eso antes de concluir."}


# ================================================================ main

def main():
    dry = "--dry" in sys.argv
    cfg = load_cfg()
    bars_by = load_tvbars(cfg)
    kl, kl_ev, labev = load_events(cfg)
    plans = load_plans(cfg)
    news = load_news(dry)
    min_date = dt.date.fromisoformat(cfg["minDate"])
    minN = cfg["minN"]
    MGMT[:] = cfg.get("mgmt", ["full"])

    def kl_at(sym, t):
        rows = kl.get(sym) or []
        best = None
        for tt, reg, aln in rows:
            if tt > t:
                break
            if t - tt <= 7200:
                best = (reg, aln)
        return best or (None, None)

    recs, days, parity = [], {}, {"compared": 0, "agree": 0, "diffs": []}
    for sym, bars in bars_by.items():
        tick = cfg["tick"].get(sym, 0.01)
        cost = cfg["costTicks"] * tick
        for date in sorted({dt.datetime.fromtimestamp(b["t"], NY).date() for b in bars}):
            if date < min_date or date.weekday() >= 5:
                continue
            t_open = at(date, cfg["nyOpen"].get(sym, cfg["nyOpen"]["default"]))
            t_close = at(date, cfg["nyClose"].get(sym, cfg["nyClose"]["default"]))
            rth = idx_range(bars, t_open, t_close)
            if not complete(rth, t_open, t_close):
                continue
            pre = [i for i, b in enumerate(bars) if b["t"] < t_open]
            pre_b = bars[pre[-1]] if pre else {}
            ctx = {"kl": kl_at, "plans": plans, "news": news, "dayOpen": bars[rth[0]]["o"]}
            n0 = len(recs)
            mk = lambda k, d, _s=sym, _dt=date, _to=t_open, _c=ctx: features(bars[k], d, _s, _dt, _to, _c)
            rep = {}
            for w in cfg["orb"]["windows"]:
                rix = idx_range(bars, t_open, t_open + w * 60)
                sess = idx_range(bars, t_open + w * 60, t_close)
                if complete(rix, t_open, t_open + w * 60, 1.0) and sess:
                    recs += [dict(r, sym=sym, date=str(date)) for r in
                             fam_breakout("ORB", bars, sess, rix, cfg["orb"], cost, mk, rep, f"{w}m")]
            t_ib = t_open + cfg["ib"]["minutes"] * 60
            ibx, sess = idx_range(bars, t_open, t_ib), idx_range(bars, t_ib, t_close)
            if complete(ibx, t_open, t_ib) and sess:
                ibrep = {}
                recs += [dict(r, sym=sym, date=str(date)) for r in
                         fam_breakout("IBB", bars, sess, ibx, cfg["ib"], cost, mk, ibrep, "IB")]
                rep["IB"] = ibrep.get("IB")
                recs += [dict(r, sym=sym, date=str(date)) for r in
                         fam_ib_levels(bars, sess, ibx, cfg, cost, mk, rep, None)]
            if pre_b:
                recs += [dict(r, sym=sym, date=str(date)) for r in
                         fam_sweep(bars, rth, pre_b, date, t_open, cfg, cost, mk, rep)]
                recs += [dict(r, sym=sym, date=str(date)) for r in
                         fam_va80(bars, rth, pre_b, cfg, cost, mk, rep)]
            recs += [dict(r, sym=sym, date=str(date)) for r in fam_pullback(bars, rth, cfg, cost, mk)]
            days[f"{sym}|{date}"] = rep
            extra = []
            for r in recs[n0:]:
                for m, a in (r.pop("alt", None) or {}).items():
                    extra.append({**r, **a, "var": f'{r["var"]}|{m}'})
            recs += extra
            for r in recs[n0:]:
                if "Rpx" in r:
                    r["cr"] = control(bars, rth, r, f'{sym}|{date}|{r["fam"]}|{r["var"]}|{r["ek"]}')
            tv = labev.get(("ORB", sym, str(date)))
            if tv:
                for w, wr in (tv.get("windows") or {"15": tv}).items():
                    mine = (rep.get(f"{w}m") or {}).get("first")
                    if mine is not None and wr.get("first") is not None:
                        parity["compared"] += 1
                        if mine == wr["first"]:
                            parity["agree"] += 1
                        else:
                            parity["diffs"].append(f"ORB|{sym}|{date}|{w}m")

    rif_sum = {"breaks": 0, "withInversion": 0}
    zevs, zdir = load_zone_events(cfg)
    zon_sum = {"touched": 0, "armed": 0, "source": "session-analyst-bus/zones/events" if zdir else None}
    for sym, bars in bars_by.items():
        crypto = sym in cfg.get("crypto", [])
        tick = cfg["tick"].get(sym, 0.01)
        cost = cfg["costTicks"] * tick
        by_date = defaultdict(list)
        for i, b in enumerate(bars):
            by_date[str(dt.datetime.fromtimestamp(b["t"], NY).date())].append(i)

        def ctx_for(k, d, _s=sym, _b=bars):
            date = dt.datetime.fromtimestamp(_b[k]["t"], NY).date()
            ctx = {"kl": kl_at, "plans": plans, "news": news, "dayOpen": None}
            return features(_b[k], d, _s, date, at(date, "09:30"), ctx)

        rr, sm = fam_range_ifvg(bars, sym, crypto, cfg, cost, ctx_for)
        for k in rif_sum:
            rif_sum[k] += sm[k]
        if zevs.get(sym):
            zr, zs = fam_zones(bars, sym, zevs[sym], crypto, cfg, cost, ctx_for)
            rr += zr
            for k in ("touched", "armed"):
                zon_sum[k] += zs[k]
        rr = [r for r in rr if dt.date.fromisoformat(r["date"]) >= min_date]
        extra = []
        for r in rr:
            for m, a in (r.pop("alt", None) or {}).items():
                extra.append({**r, **a, "var": f'{r["var"]}|{m}'})
        rr += extra
        for r in rr:
            if "Rpx" in r:
                pool = by_date.get(r["date"]) or []
                r["cr"] = control(bars, pool, r, f'{sym}|{r["date"]}|{r["fam"]}|{r["var"]}|{r["ek"]}')
        recs += rr

    lab = {}
    comboN = cfg.get("comboMinN", 2 * minN)
    wf = cfg.get("walkForward", {})
    for fam in ("ORB", "IBB", "IBL", "IBR", "SWR", "SWC", "VA80", "PB", "RIF", "RBO", "ZON"):
        bucketize([r for r in recs if r["fam"] == fam])
    for fam in ("ORB", "IBB", "IBL", "SWR", "SWC", "VA80", "PB", "RIF", "RBO", "ZON"):
        fr = [r for r in recs if r["fam"] == fam]
        if fr:
            lab[fam] = {**rank(fr, minN, comboN), "confluence": feature_effect(fr, minN),
                        "walkForward": walk_forward(fr, minN, comboN, wf.get("inSampleFrac", 0.6), wf.get("minDays", 20)),
                        "bySym": {s: stats([r for r in fr if r["sym"] == s]) for s in sorted({r["sym"] for r in fr})}}
    ibr = [r for r in recs if r["fam"] == "IBR"]
    ib_levels = {}
    for name in sorted({r["var"] for r in ibr}, key=lambda x: float(x[2:])):
        rows = [r for r in ibr if r["var"] == name]
        ib_levels[name] = {**respect_stats(rows), "control": rows[0].get("ctrl", False)}
    ctrl_rows = [r for r in ibr if r.get("ctrl")]
    va = [v["va80"] for v in days.values() if "va80" in v]
    outside = [v for v in va if v["open"] != "inside"]
    sig = [v for v in outside if v.get("reentry")]
    pctf = lambda xs, k: round(100 * sum(bool(x.get(k)) for x in xs) / len(xs), 1) if xs else None
    va80 = {"days": len(va), "openOutside": len(outside), "reentryPct": pctf(outside, "reentry"),
            "afterReentry": {"n": len(sig), "reachedPocPct": pctf(sig, "reachedPoc"), "reachedFarPct": pctf(sig, "reachedFar")},
            "control": {"insideDaysTouchBothPct": pctf([v for v in va if v["open"] == "inside"], "touchedBoth"),
                        "allDaysTouchBothPct": pctf(va, "touchedBoth")}}
    if "PB" in lab:
        lab["PB"]["trendTest"] = trend_split([r for r in recs if r["fam"] == "PB"], minN)
    out = {
        "_writer": "lab", "_schema": 2,
        "asOf": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "minDate": cfg["minDate"], "minN": minN, "costTicks": cfg["costTicks"],
        "data": {"tvbarDays": len(days), "bySym": {s: sum(k.startswith(s + "|") for k in days) for s in cfg["symbols"]},
                 "trades": sum(1 for r in recs if "r" in r), "source": "tdl_feed (TradingView)",
                 "collection": collection(cfg), "walkForwardMinDays": cfg.get("walkForward", {}).get("minDays", 20)},
        "lab": lab,
        "va80": va80,
        "zones": {**zon_sum, "byEntry": zone_entry_table(lab)},
        "rangeIfvg": {**rif_sum, "inversionPct": round(100 * rif_sum["withInversion"] / rif_sum["breaks"], 1) if rif_sum["breaks"] else None,
                      "vsBreakout": vs_rbo(lab)},
        "ibLevels": {"levels": ib_levels, "controlAvg": respect_stats(ctrl_rows) if ctrl_rows else None},
        "klLevels": kl_lab(kl_ev, minN),
        "parity": {**parity, "diffs": parity["diffs"][-20:]},
        "lastDays": dict(sorted(days.items())[-10:]),
    }
    if dry:
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return
    path = os.path.join(ROOT, "live", "lab.json")
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
        if {k: v for k, v in prev.items() if k != "asOf"} == {k: v for k, v in out.items() if k != "asOf"}:
            print("lab: sin cambios")
            return
    except (OSError, ValueError):
        pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"lab: {out['data']['tvbarDays']} sym-dias, {out['data']['trades']} operaciones simuladas, "
          f"{out['klLevels']['touches']} toques TDL KL -> live/lab.json")


if __name__ == "__main__":
    main()
