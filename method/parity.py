#!/usr/bin/env python3
"""parity.py - Registro de paridad del Paso 4 del Trader OS.

Compara el plan de Contexto (live/plan.json de ESTE bus) contra el Session Analyst
viejo (plans/latest.json del session-analyst-bus, publico). Por instrumento mira si
el 'verdict.signal' (GO / WAIT / AVOID) coincide. Anexa una entrada por ciclo a
state/parity-log.jsonl (idempotente por date+runType) y recomputa live/parity.json con
el acumulado de una ventana movil (14 dias) y la evaluacion del criterio de corte.

Es el termometro para decidir cuando apagar uno de los dos (Paso 4). Ver method/parity.md.

Best-effort: NUNCA lanza. Si algo falla imprime 'parity: <motivo>' y sale 0, para no
romper el pre-asia. Sin dependencias externas (solo stdlib).

Uso:  python3 method/parity.py        (desde la raiz del repo)
"""
import json, os, sys, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SA_URL = "https://raw.githubusercontent.com/jesusreyna2016/session-analyst-bus/main/plans/latest.json"
SYMS = ["NQ", "ES", "GC", "YM", "CL"]
WINDOW = 14        # dias de la ventana movil
AGREE_TARGET = 90  # % de acuerdo del criterio
MIN_DAYS = 10      # dias minimos en ventana para declarar el criterio


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sig(plan, sym):
    try:
        v = plan["instruments"][sym]["verdict"]["signal"]
        return v if v else None
    except Exception:
        return None


def main():
    plan_path = os.path.join(ROOT, "live", "plan.json")
    try:
        ctx = _read_json(plan_path)
    except Exception as e:
        print("parity: sin live/plan.json (%s), nada que comparar" % e)
        return 0
    try:
        req = urllib.request.Request(SA_URL, headers={"User-Agent": "tos-parity"})
        with urllib.request.urlopen(req, timeout=20) as r:
            sa = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("parity: no pude leer el SA (%s), me salto este ciclo" % e)
        return 0

    date = ctx.get("date") or datetime.date.today().isoformat()
    run_type = ctx.get("runType") or "pre-asia"
    by = {}
    n_both = n_match = 0
    for s in SYMS:
        c = _sig(ctx, s)
        a = _sig(sa, s)
        row = {"ctx": c, "sa": a}
        if c and a:
            row["match"] = (c == a)
            n_both += 1
            if c == a:
                n_match += 1
        by[s] = row
    agree = round(100 * n_match / n_both) if n_both else None
    entry = {
        "date": date, "runType": run_type,
        "ctxAt": ctx.get("generatedAt"), "saAt": sa.get("generatedAt"),
        "by": by, "nBoth": n_both, "nMatch": n_match, "agreePct": agree,
    }

    # state/parity-log.jsonl, idempotente por date+runType
    log_path = os.path.join(ROOT, "state", "parity-log.jsonl")
    rows = []
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("date") == date and o.get("runType") == run_type:
                    continue  # lo reemplaza la entrada de este ciclo
                rows.append(o)
    rows.append(entry)
    rows.sort(key=lambda o: (o.get("date", ""), o.get("runType", "")))
    with open(log_path, "w", encoding="utf-8") as f:
        for o in rows:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    # ventana: ultimas WINDOW fechas distintas
    dates = []
    for o in rows:
        d = o.get("date")
        if d and d not in dates:
            dates.append(d)
    win_dates = set(sorted(dates)[-WINDOW:])
    win = [o for o in rows if o.get("date") in win_dates]
    w_both = sum(o.get("nBoth", 0) for o in win)
    w_match = sum(o.get("nMatch", 0) for o in win)
    w_agree = round(100 * w_match / w_both) if w_both else None
    per = {}
    for s in SYMS:
        tb = tm = 0
        for o in win:
            r = (o.get("by") or {}).get(s) or {}
            if r.get("ctx") and r.get("sa"):
                tb += 1
                if r.get("match"):
                    tm += 1
        per[s] = {"n": tb, "agreePct": (round(100 * tm / tb) if tb else None)}
    n_days = len(win_dates)
    meets = (n_days >= MIN_DAYS and w_agree is not None and w_agree >= AGREE_TARGET)
    summary = {
        "schema": "parity-1",
        "builtAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "windowDays": WINDOW, "daysInWindow": n_days,
        "agreePct": w_agree, "nBoth": w_both,
        "byInstrument": per,
        "today": {"date": date, "runType": run_type, "agreePct": agree, "by": by, "nBoth": n_both},
        "criterion": {
            "agreeTarget": AGREE_TARGET, "minDays": MIN_DAYS,
            "verdictAgreeMet": bool(meets),
            "readyToCut": False,
            "note": ("Paso 4: >=90% mismo verdict por instrumento en >=10 dias de la ventana. "
                     "Falta cruzar E[R] calificado igual o mejor (fase 2) antes del corte; "
                     "readyToCut se decide a mano."),
        },
    }
    with open(os.path.join(ROOT, "live", "parity.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    print("parity: hoy %s/%s coinciden (%s%%); ventana %s dias, %s%% [%s]" % (
        n_match, n_both, agree, n_days, w_agree,
        "criterio verdict OK" if meets else "aun no"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # jamas romper el pipeline del pre-asia
        print("parity: error no fatal (%s)" % e)
        sys.exit(0)
