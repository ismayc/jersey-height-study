"""Explainer diagrams for the story page, drawn with the family's famdiagram
(../basketball-analysis-tools/famdiagram.py) and saved to figures/<ref>.svg
(plus a <ref>_narrow.svg phone layout). report_builder.py inlines them.

Every number drawn is read from a committed table: the season metrics and
models in output/ (reconciled with R by python/04_reconcile.py) and, for the
scatter in dg3, the committed roster file data/nba_rosters.csv cleaned by
python/03_analysis.py's own load_players(). dg3 recomputes each panel's
correlation from those rows and refuses to draw if it differs from
output/results_python.csv.

Diagrams:
  dg1_height_steps   the 2002-03 to latest-season height decline split into
                     the slow drift, the one-offseason 2019-20 step, and the
                     rise since, with the regime model's step estimate
                     (output/results_python.csv, output/models_python.csv)
  dg2_same_players   the within-player check: every player rostered in both
                     2018-19 and 2019-20, by how his listed height changed,
                     beside the share listed shorter in every offseason
                     (output/within_player_python.csv)
  dg3_number_height  what the jersey/height correlation measures: each
                     player as a dot in the first and the latest season,
                     centers marked (data/nba_rosters.csv,
                     output/results_python.csv)

Run:     python python/14_diagrams.py
--check: rebuild every SVG in memory and fail if a committed one differs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIG = ROOT / "figures"
sys.path.insert(0, str(ROOT.parent / "basketball-analysis-tools"))
import famdiagram as fd  # noqa: E402

STEP_PAIR = 2018          # the 2018-19 -> 2019-20 offseason, the rule change
MINUS = "−"


def analysis_module():
    spec = importlib.util.spec_from_file_location(
        "jersey_analysis", ROOT / "python" / "03_analysis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def season(y: int) -> str:
    return f"{y}-{str(y + 1)[-2:]}"


def signed(v: float, d: int = 2) -> str:
    s = f"{abs(v):.{d}f}"
    if float(s) == 0:
        return s
    return ("+" if v > 0 else MINUS) + s


def pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def wrap(s: str, width: float, size: float) -> list[str]:
    """Greedy word wrap on an estimated glyph width."""
    per = size * 0.55
    out, cur = [], ""
    for w in s.split():
        t = f"{cur} {w}".strip()
        if len(t) * per > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def para(d: fd.Diagram, x, y, s, width, size, lh=None, **kw) -> float:
    """Wrapped text; returns the baseline of the last line."""
    lh = lh or size * 1.35
    lines = wrap(s, width, size)
    for i, line in enumerate(lines):
        d.text(x, y + i * lh, line, size=size, **kw)
    return y + (len(lines) - 1) * lh


# ---------------------------------------------------------------- dg1
def height_steps(narrow: bool) -> fd.Diagram:
    res = pl.read_csv(OUT / "results_python.csv")
    h = res.filter(pl.col("metric") == "mean_height_in").sort("season_start")
    by = dict(zip(h["season_start"].to_list(), h["value"].to_list()))
    peak = int(h.sort("value", descending=True)["season_start"][0])
    last = int(h["season_start"][-1])
    a, b, c, z = by[peak], by[STEP_PAIR], by[STEP_PAIR + 1], by[last]
    drift, step, since, net = b - a, c - b, z - c, z - a
    share = abs(step) / abs(net)
    sh = (pl.read_csv(OUT / "models_python.csv")
          .filter((pl.col("model") == "height_regime") & (pl.col("term") == "shift2019"))
          .row(0, named=True))

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (16, 14, 20)
    pad = 12
    d = fd.Diagram(W, 10, "The height decline split into a slow drift, one step, and a rise")
    y = 28
    d.text(pad, y, f"Mean listed height, {season(peak)} peak to {season(last)}",
           size=head, display=True, weight="600")
    # plot geometry
    px0 = pad + 44
    pw = (W - px0 - pad) if narrow else 470
    top, ph = y + 44, 230 if narrow else 250
    lo_v = min(a, b, c, z) - 0.25
    hi_v = max(a, b, c, z) + 0.2

    def Y(v: float) -> float:
        return top + ph * (hi_v - v) / (hi_v - lo_v)

    # axis: whole inches inside the range
    # axis: every half inch inside the range
    for half in range(int(lo_v * 2) + 1, int(hi_v * 2) + 1):
        tick = half / 2
        d.line(px0, Y(tick), px0 + pw, Y(tick), stroke="rule", sw=1)
        d.text(px0 - 6, Y(tick) + 4, f"{tick:g}", size=small, fill="ink3", anchor="end")
    d.text(pad, top - 14, "inches", size=small, fill="ink3")
    cols = [
        ("level", a, a, season(peak), "peak", "ink"),
        ("delta", a, b, f"{STEP_PAIR - peak} seasons", "slow drift", "ink3"),
        ("delta", b, c, "one offseason", "rule change", "c8"),
        ("delta", c, z, f"{last - STEP_PAIR - 1} seasons", "since", "c3"),
        ("level", z, z, season(last), "now", "ink"),
    ]
    cw = pw / len(cols)
    bw = cw * (0.5 if narrow else 0.46)
    for i, (kind, v0, v1, lab1, lab2, col) in enumerate(cols):
        cx = px0 + cw * i + cw / 2
        if kind == "level":
            d.line(cx - bw / 2, Y(v0), cx + bw / 2, Y(v0), stroke="ink", sw=3)
            d.text(cx, Y(v0) - 8, f"{v0:.2f}", size=fs, fill="ink", anchor="middle",
                   weight="700")
        else:
            y0, y1 = sorted((Y(v0), Y(v1)))
            d.rect(cx - bw / 2, y0, bw, max(y1 - y0, 2), fill=col, rx=2,
                   opacity=0.85 if col != "ink3" else 0.7)
            delta = v1 - v0
            ly = (y1 + 17) if delta < 0 else (y0 - 8)
            d.text(cx, ly, signed(delta), size=fs, anchor="middle", weight="700",
                   fill="c8" if col == "c8" else "ink")
        # connector to the next column
        if i < len(cols) - 1:
            d.line(cx + bw / 2, Y(v1), cx + cw - bw / 2, Y(v1), stroke="ink3", sw=1,
                   dash="3 3")
        # On a phone the columns are too narrow for two-word labels on one line.
        lines = ([(w, "ink", "600") for w in lab2.split()]
                 + [(w, "ink3", None) for w in lab1.split()]) if narrow else \
            [(lab2, "ink", "600"), (lab1, "ink3", None)]
        for j, (s, col, wt) in enumerate(lines):
            d.text(cx, top + ph + 20 + j * small * 1.3, s, size=small, fill=col,
                   anchor="middle", weight=wt)
        n_lines = max(n_lines, len(lines)) if i else len(lines)
    yb = top + ph + 20 + (n_lines - 1) * small * 1.3

    # callout
    if narrow:
        bx, by0, bwid = pad, yb + 22, W - 2 * pad
    else:
        bx, by0, bwid = px0 + pw + 22, top - 6, W - (px0 + pw + 22) - pad
    tx = bx + 14
    tw = bwid - 28
    box_at = len(d.parts)
    yy = by0 + 44
    d.text(tx, yy, pct(share), size=38, display=True, weight="700", fill="c8")
    yy = para(d, tx, yy + 26, f"of the net {signed(net)} in decline happened in the "
              f"one offseason when the league began requiring heights measured "
              f"without shoes.", tw, fs, fill="ink")
    yy = para(d, tx, yy + 30, "The regime model fits that step directly:", tw, small,
              fill="ink2")
    d.text(tx, yy + 24, f"{signed(sh['estimate'])} in", size=fs + 5, fill="c8",
           weight="700")
    yy = para(d, tx, yy + 46, f"95% CI {signed(sh['conf.low'])} to "
              f"{signed(sh['conf.high'])}", tw, small, fill="ink3")
    bh = yy + 18 - by0
    # The box is sized by its text, so draw it last and slot it in behind.
    d.rect(bx, by0, bwid, bh, fill="surface2", stroke="rule", rx=8)
    d.parts.insert(box_at, d.parts.pop())
    d.h = max(yb, by0 + bh) + 16
    return d


# ---------------------------------------------------------------- dg2
def same_players(narrow: bool) -> fd.Diagram:
    wp = pl.read_csv(OUT / "within_player_python.csv").sort("pair_start")
    r = wp.filter(pl.col("pair_start") == STEP_PAIR).row(0, named=True)
    n = int(r["n_matched"])
    k_short = round(r["share_shrunk"] * n)
    k_grew = round(r["share_grew"] * n)
    k_same = n - k_short - k_grew
    others = wp.filter(pl.col("pair_start") != STEP_PAIR)
    typical = float(others["share_shrunk"].median())

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (16, 14, 20)
    pad = 12
    d = fd.Diagram(W, 10, "The same players, listed before and after the 2019-20 rule")
    y = 28
    last = para(d, pad, y, f"The same {n} players, listed in {season(STEP_PAIR)} "
                f"and again in {season(STEP_PAIR + 1)}", W - 2 * pad, head,
                display=True, weight="600")
    y = last + 22
    # legend
    leg = [("c8", f"listed shorter: {k_short}"), ("ink3", f"unchanged: {k_same}"),
           ("c3", f"listed taller: {k_grew}")]
    lx = pad
    for col, lab in leg:
        if narrow and lx + len(lab) * small * 0.55 + 30 > W:
            lx, y = pad, y + 20
        d.circle(lx + 6, y - 4, 6, fill=col)
        d.text(lx + 17, y, lab, size=small, fill="ink2")
        lx += 17 + len(lab) * small * 0.55 + 18
    y += 18
    # unit chart: one dot per player
    per_row = 25 if narrow else 20
    sp = (W - 2 * pad) / per_row if narrow else 12.5
    rad = sp * 0.36
    colors = ["c8"] * k_short + ["ink3"] * k_same + ["c3"] * k_grew
    for i, col in enumerate(colors):
        cx = pad + sp / 2 + (i % per_row) * sp
        cy = y + sp / 2 + (i // per_row) * sp
        d.circle(cx, cy, rad, fill=col, opacity=0.9 if col != "ink3" else 0.55)
    rows = (n + per_row - 1) // per_row
    grid_bottom = y + rows * sp
    yy = grid_bottom + 22
    d.text(pad, yy, f"Mean change per player: {signed(r['mean_delta'])} in",
           size=fs, fill="ink", weight="700")
    yy = para(d, pad, yy + 20, "Same people, so a change in who plays cannot "
              "explain the drop.", (W - 2 * pad) if narrow else 240, small,
              fill="ink3", italic=True)
    left_end = yy

    # strip: share listed shorter, every offseason
    if narrow:
        sx, sy, sw_ = pad, left_end + 40, W - 2 * pad
    else:
        sx, sy, sw_ = 300, 74, W - 300 - pad
    sy = para(d, sx, sy, "Returning players listed shorter, "
              "each offseason", sw_, fs, fill="ink", weight="600")
    ph = 150
    base = sy + 24 + ph
    vmax = float(wp["share_shrunk"].max())
    bw = sw_ / wp.height
    for i, rr in enumerate(wp.iter_rows(named=True)):
        hgt = ph * rr["share_shrunk"] / vmax
        hit = rr["pair_start"] == STEP_PAIR
        d.rect(sx + i * bw + bw * 0.12, base - max(hgt, 1), bw * 0.76, max(hgt, 1),
               fill="c8" if hit else "ink3", opacity=0.9 if hit else 0.6)
        if hit:
            hx = sx + i * bw + bw / 2
            d.text(hx - bw, base - hgt + 12, f"{season(STEP_PAIR)} to "
                   f"{season(STEP_PAIR + 1)}: {pct(rr['share_shrunk'])}",
                   size=small, fill="c8", anchor="end", weight="700")
    ty = base - ph * typical / vmax
    d.line(sx, ty, sx + sw_, ty, stroke="ink2", sw=1, dash="4 3")
    d.text(sx, ty - 6, f"median of the other {others.height}: {pct(typical)}",
           size=small, fill="ink2")
    d.line(sx, base, sx + sw_, base, stroke="rule", sw=1)
    first, lastp = int(wp["pair_start"][0]), int(wp["pair_start"][-1])
    d.text(sx, base + 18, f"{season(first)} to {season(first + 1)}", size=small,
           fill="ink3")
    d.text(sx + sw_, base + 18, f"{season(lastp)} to {season(lastp + 1)}",
           size=small, fill="ink3", anchor="end")
    d.h = max(left_end, base + 18) + 18
    return d


# ---------------------------------------------------------------- dg3
def _jitter(key: str, salt: str, amp: float) -> float:
    """Deterministic jitter so overlapping integer values separate."""
    h = hashlib.sha256(f"{key}|{salt}".encode()).digest()
    return (h[0] / 255 - 0.5) * 2 * amp


def number_height(narrow: bool) -> fd.Diagram:
    m = analysis_module()
    players = m.load_players().filter(pl.col("jersey_num").is_not_null())
    res = pl.read_csv(OUT / "results_python.csv").filter(
        pl.col("metric") == "jersey_height_cor")
    first = int(res["season_start"].min())
    last = int(res["season_start"].max())
    panels = []
    for s in (first, last):
        p = players.filter(pl.col("season_start") == s)
        r_pub = float(res.filter(pl.col("season_start") == s)["value"][0])
        r_now = float(p.select(pl.corr("jersey_num", "height_in")).item())
        if abs(r_now - r_pub) > 1e-9:
            raise SystemExit(f"dg3: {s} correlation {r_now} != published {r_pub}")
        panels.append((s, p, r_pub))
    num_max = max(float(p["jersey_num"].max()) for _, p, _ in panels)
    xmax = (int(num_max) // 10 + 1) * 10
    hts = [v for _, p, _ in panels for v in p["height_in"].to_list()]
    ylo, yhi = min(hts) - 1, max(hts) + 1

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (16, 14, 20)
    pad = 12
    d = fd.Diagram(W, 10, "Each player as a dot: jersey number against listed height")
    y = 26
    y = para(d, pad, y, "Each dot is one player: his jersey number across, his "
             "listed height up", W - 2 * pad, fs, fill="ink2")
    y += 22
    d.circle(pad + 6, y - 4, 5, fill="nba")
    d.text(pad + 16, y, "centers", size=small, fill="ink2")
    d.circle(pad + 86, y - 4, 5, fill="ink3", opacity=0.6)
    d.text(pad + 96, y, "guards and forwards", size=small, fill="ink2")
    d.line(pad + 250 if not narrow else pad + 236, y - 4,
           pad + 274 if not narrow else pad + 258, y - 4, stroke="ink", sw=2)
    d.text(pad + 280 if not narrow else pad + 264, y, "best-fit line", size=small,
           fill="ink2")
    y += 16
    gw = (W - 2 * pad - 40) if narrow else (W - 2 * pad - 40 - 40) / 2
    ph = 200
    for k, (s, p, r) in enumerate(panels):
        if narrow:
            gx, gy = pad + 40, y + 30 + k * (ph + 92)
        else:
            gx, gy = pad + 40 + k * (gw + 40), y + 30

        def X(v):
            return gx + gw * v / xmax

        def Y(v):
            return gy + ph * (yhi - v) / (yhi - ylo)

        d.text(gx, gy - 12, f"{season(s)}", size=head, display=True, weight="700")
        d.text(gx + gw, gy - 12, f"r = {signed(r)}", size=head, display=True,
               weight="700", fill="nba", anchor="end")
        d.rect(gx, gy, gw, ph, fill="surface2", opacity=0.5)
        for ft in range(int(ylo) // 6 * 6 + 6, int(yhi) + 1, 6):
            d.line(gx, Y(ft), gx + gw, Y(ft), stroke="rule", sw=1)
            d.text(gx - 5, Y(ft) + 4, f"{ft // 12}'{ft % 12}\"", size=small,
                   fill="ink3", anchor="end")
        for t in range(0, xmax + 1, 25 if xmax > 60 else 10):
            d.text(X(t), gy + ph + 16, str(t), size=small, fill="ink3",
                   anchor="middle")
        # non-centers first so centers sit on top
        rows = sorted(p.iter_rows(named=True), key=lambda q: q["position_group"] == "C")
        for q in rows:
            key = f"{q['PLAYER_ID']}|{s}"
            cx = X(q["jersey_num"] + _jitter(key, "x", 0.45))
            cy = Y(q["height_in"] + _jitter(key, "y", 0.3))
            if q["position_group"] == "C":
                d.circle(cx, cy, 2.6, fill="nba", opacity=0.8)
            else:
                d.circle(cx, cy, 2.4, fill="ink3", opacity=0.45)
        xs = p["jersey_num"].to_list()
        ys = p["height_in"].to_list()
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        slope = (sum((a - mx) * (b - my) for a, b in zip(xs, ys))
                 / sum((a - mx) ** 2 for a in xs))
        x0, x1 = 0.0, max(xs)
        d.line(X(x0), Y(my + slope * (x0 - mx)), X(x1), Y(my + slope * (x1 - mx)),
               stroke="ink", sw=2)
        d.text(gx + gw / 2, gy + ph + 34, "jersey number", size=small, fill="ink3",
               anchor="middle")
    end = (y + 30 + 2 * (ph + 92) - 92 + 40) if narrow else (y + 30 + ph + 40)
    end = para(d, pad, end + 26, "The more the cloud climbs from low numbers to high, "
               "the larger r: the number tells you more about the height.", W - 2 * pad, fs, fill="ink2")
    d.h = end + 14
    return d


DIAGRAMS = {"dg1_height_steps": height_steps, "dg2_same_players": same_players,
            "dg3_number_height": number_height}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        fails = []
        with tempfile.TemporaryDirectory() as tmp:
            for ref, fn in DIAGRAMS.items():
                for p in fd.save(Path(tmp), ref, fn(False), fn(True)):
                    old = FIG / p.name
                    if not old.exists() or old.read_text() != p.read_text():
                        fails.append(p.name)
        for f in fails:
            print("FAIL", f, "differs from a fresh build")
        print("DIAGRAMS", "FAILED" if fails else
              f"PASSED: {len(DIAGRAMS)} diagrams rebuild identically")
        return 1 if fails else 0
    for ref, fn in DIAGRAMS.items():
        for p in fd.save(FIG, ref, fn(False), fn(True)):
            print("wrote", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
