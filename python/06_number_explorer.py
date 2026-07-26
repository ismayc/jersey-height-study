"""Exploratory jersey-number analysis, season by season.

Two views the main study's conventions figure aggregates away:

  1. the median jersey number by season (with quartiles), 1980-81 through
     2024-25;
  2. the full number distribution per season, browsable with a slider
     (one frame per season) and a play button.

Number-parsing rules, applied identically everywhere and gated below:
  - "0" and "00" are POOLED into a single 0/00 bucket. They are distinct
    uniforms on a roster but the same number choice culturally, and the
    pooling is noted on every surface that shows it.
  - A handful of entries list several numbers for one season ("3-12-44");
    the first listed is used.
  - Blank/missing numbers are dropped and counted.

Outputs:  output/number_by_season.csv     per-season median/quartiles/shares
          output/number_explorer_validation.csv
          figures/fig5_median_number.html
          figures/fig6_number_histogram.html (slider + play)

Run:  python python/06_number_explorer.py           full build
      python python/06_number_explorer.py --check   offline gate replay
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nba_rosters.csv"
OUT = ROOT / "output"
FIG = ROOT / "figures"
WEARER_LIST_MAX = 10


def load_numbers() -> tuple[pl.DataFrame, dict]:
    raw = pl.read_csv(DATA, infer_schema_length=0)
    parsed = (raw.with_columns(num_txt=pl.col("NUM").str.strip_chars())
              .with_columns(first_tok=pl.col("num_txt")
                            .str.extract(r"^(\d+)", 1)))
    dropped = parsed.filter(pl.col("first_tok").is_null()).height
    multi = parsed.filter(pl.col("num_txt").str.contains(r"^\d+-")).height
    # first-token rule: "0-6" and "00-10" (multi-number seasons) pool too
    pooled_00 = parsed.filter(pl.col("num_txt")
                              .str.contains(r"^00(-|$)")).height
    pooled_0 = parsed.filter(pl.col("num_txt")
                             .str.contains(r"^0(-|$)")).height
    df = (parsed.filter(pl.col("first_tok").is_not_null())
          .with_columns(number=pl.col("first_tok").cast(pl.Int64),
                        season_start=pl.col("season_start").cast(pl.Int64))
          .select("season_start", "number", "PLAYER", "team_abbrev"))
    notes = {"dropped_blank": dropped, "multi_number_entries": multi,
             "pooled_0": pooled_0, "pooled_00": pooled_00,
             "kept": df.height, "raw": raw.height}
    return df, notes


def by_season(df: pl.DataFrame) -> pl.DataFrame:
    return (df.group_by("season_start")
            .agg(n=pl.len(),
                 median_number=pl.col("number").median(),
                 q25=pl.col("number").quantile(0.25),
                 q75=pl.col("number").quantile(0.75),
                 share_0_00=(pl.col("number") == 0).mean(),
                 share_50_plus=(pl.col("number") >= 50).mean())
            .sort("season_start")
            .with_columns(season=pl.format("{}-{}",
                                           pl.col("season_start"),
                                           (pl.col("season_start") + 1)
                                           .cast(pl.String)
                                           .str.slice(2, 2))))


def gates(df: pl.DataFrame, seasons: pl.DataFrame, notes: dict
          ) -> pl.DataFrame:
    rows = [
        {"check": "kept + dropped rows account for every roster row",
         "value": abs(notes["kept"] + notes["dropped_blank"]
                      - notes["raw"]), "threshold": 0},
        {"check": "per-season counts sum to the kept total",
         "value": abs(int(seasons["n"].sum()) - notes["kept"]),
         "threshold": 0},
        {"check": "pooled 0/00 bucket equals the raw '0' + '00' counts",
         "value": abs(df.filter(pl.col("number") == 0).height
                      - (notes["pooled_0"] + notes["pooled_00"])),
         "threshold": 0},
        {"check": "independent median re-derivation agrees (max |diff|)",
         "value": float(max(
             abs(float(seasons.filter(pl.col("season_start") == s)
                       ["median_number"][0])
                 - float(sorted(df.filter(pl.col("season_start") == s)
                                ["number"].to_list())[
                     len(df.filter(pl.col("season_start") == s)) // 2]
                     if len(df.filter(pl.col("season_start") == s)) % 2
                     else (lambda v, m: (v[m - 1] + v[m]) / 2)(
                         sorted(df.filter(pl.col("season_start") == s)
                                ["number"].to_list()),
                         len(df.filter(pl.col("season_start") == s)) // 2)))
             for s in seasons["season_start"].to_list())),
         "threshold": 1e-9},
    ]
    return pl.DataFrame(rows).with_columns(
        passed=pl.col("value") <= pl.col("threshold"))


FIG6_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
html,body{margin:0;height:100%;font:14px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;color:#2a3f5f}
.controls{display:flex;gap:.8rem;align-items:center;padding:.5rem .9rem 0;flex-wrap:wrap}
.controls input[type=range]{flex:1;min-width:180px}
.controls button{border:1px solid #c8d4e3;background:#fff;border-radius:6px;padding:.25rem .6rem;cursor:pointer;color:#2a3f5f}
.controls button.on{background:#1E3A5F;color:#fff;border-color:#1E3A5F}
.seasonlab{font-weight:700;min-width:5.2em}
#plot{width:100%;height:calc(100% - 44px)}
</style>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
</head><body>
<div class="controls">
  <button id="play">Play</button>
  <span class="seasonlab" id="lab"></span>
  <input type="range" id="season" min="0" max="45" value="0" step="1">
  <span>bin size:</span>
  <button class="bin on" data-b="1">1</button>
  <button class="bin" data-b="5">5</button>
  <button class="bin" data-b="10">10</button>
</div>
<div id="plot"></div>
<script>
const P = __PAYLOAD__;
let season = 0, bin = 1, timer = null;
const gd = document.getElementById('plot');
document.getElementById('season').max = P.labels.length - 1;
const ymax = {};
for (const b of [1,5,10]) {
  let m = 0;
  for (const d of P.data)
    for (let i = 0; i < 100; i += b)
      m = Math.max(m, d.c.slice(i, i+b).reduce((a,v)=>a+v,0));
  ymax[b] = m + 4;
}
function binLabel(i, b){
  if (b === 1) return i === 0 ? '0/00' : String(i);
  const hi = Math.min(i+b-1, 99);
  return (i === 0 ? '0/00' : String(i)) + '\u2013' + hi;
}
function render(){
  const d = P.data[season], xs = [], ys = [], cd = [];
  for (let i = 0; i < 100; i += bin) {
    const n = d.c.slice(i, i+bin).reduce((a,v)=>a+v,0);
    let names = [];
    for (let j = i; j < Math.min(i+bin,100); j++) {
      if (d.w[j] === null) { names = null; break; }
      names = names.concat(d.w[j]);
    }
    let extra = '';
    if (names && n > 0 && names.length <= P.maxList)
      extra = names.length === 1 ? '<br>only wearer: ' + names[0]
            : '<br>wearers:<br>' + names.join('<br>');
    xs.push(binLabel(i, bin)); ys.push(n);
    cd.push([binLabel(i, bin), extra]);
  }
  const tickEvery = bin === 1 ? 5 : 1;
  Plotly.react(gd, [{type:'bar', x:xs, y:ys, customdata:cd,
    marker:{color:'#1E3A5F', line:{color:'white', width:1}},
    hovertemplate:'number %{customdata[0]}<br>%{y} players%{customdata[1]}<extra></extra>'}],
   {title:{text:'Who wears what: jersey-number distribution, one season at a time (0 and 00 pooled)'},
    xaxis:{title:{text:'jersey number'}, type:'category',
           tickmode:'array',
           tickvals:xs.filter((_,k)=>k % tickEvery === 0)},
    yaxis:{title:{text:'players'}, range:[0, ymax[bin]]},
    template:'plotly_white', plot_bgcolor:'#fff', paper_bgcolor:'#fff',
    margin:{l:60,r:30,t:60,b:60}},
   {responsive:true, displaylogo:false});
  document.getElementById('lab').textContent = P.labels[season];
  document.getElementById('season').value = season;
}
document.getElementById('season').addEventListener('input', e => {
  season = +e.target.value; render();
});
for (const btn of document.querySelectorAll('.bin'))
  btn.addEventListener('click', () => {
    bin = +btn.dataset.b;
    document.querySelectorAll('.bin').forEach(b => b.classList.toggle('on', b === btn));
    render();
  });
document.getElementById('play').addEventListener('click', () => {
  if (timer) { clearInterval(timer); timer = null;
    document.getElementById('play').textContent = 'Play'; return; }
  document.getElementById('play').textContent = 'Pause';
  timer = setInterval(() => {
    season = (season + 1) % P.labels.length;
    render();
    if (season === P.labels.length - 1) { clearInterval(timer); timer = null;
      document.getElementById('play').textContent = 'Play'; }
  }, 350);
});
render();
</script></body></html>
"""


def figures(df: pl.DataFrame, seasons: pl.DataFrame) -> None:
    import plotly.graph_objects as go

    # --- fig5: median with quartile band ------------------------------------
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=seasons["season"], y=seasons["q75"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=seasons["season"], y=seasons["q25"], mode="lines",
        line=dict(width=0), fill="tonexty",
        fillcolor="rgba(30,58,95,0.12)", name="25th-75th percentile",
        hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=seasons["season"], y=seasons["median_number"],
        mode="lines+markers", name="median number",
        line=dict(color="#1E3A5F", width=2), marker=dict(size=5),
        customdata=seasons.select("share_0_00", "share_50_plus").to_numpy(),
        hovertemplate=("%{x}<br>median %{y}<br>0/00 share "
                       "%{customdata[0]:.1%} · 50+ share "
                       "%{customdata[1]:.1%}<extra></extra>")))
    fig.update_layout(
        title="Median jersey number by season, 1980-81 through 2024-25 "
              "(0 and 00 pooled)",
        xaxis_title="season", yaxis_title="jersey number",
        template="plotly_white", legend=dict(orientation="h", y=1.02,
                                             x=0, yanchor="bottom"))
    # type="category" is load-bearing: plotly parses "2010-11" as the date
    # November 2010 otherwise, mangling the axis into months and days
    fig.update_xaxes(type="category",
                     tickvals=[s for s in seasons["season"]
                               if int(s[:4]) % 5 == 0])
    fig.write_html(FIG / "fig5_median_number.html", include_plotlyjs="cdn")

    # --- fig6: per-season histogram, custom HTML -----------------------------
    # Season slider + play + ADJUSTABLE BIN SIZE (1/5/10). Plotly frames
    # cannot carry a second control dimension, so the raw per-number counts
    # are embedded and a small vanilla-JS layer recomputes bins on the fly.
    # Wearer names are kept per number (when 10 or fewer wore it) so a
    # coarser bin can still list its wearers when the aggregate stays <= 10.
    import json

    per_player = (df.group_by("season_start", "number", "PLAYER")
                  .agg(teams=pl.col("team_abbrev").unique().sort()
                       .str.join(", "))
                  .with_columns(entry=pl.format("{} ({})", pl.col("PLAYER"),
                                                pl.col("teams"))))
    grouped = (per_player.group_by("season_start", "number")
               .agg(n_players=pl.len(), entries=pl.col("entry").sort())
               .join(df.group_by("season_start", "number").agg(n=pl.len()),
                     on=["season_start", "number"]))

    season_list = sorted(seasons["season_start"].to_list())
    labels = [seasons.filter(pl.col("season_start") == s0)["season"][0]
              for s0 in season_list]
    data = []
    for s0 in season_list:
        g = {num: (n, ent if len(ent) <= WEARER_LIST_MAX else None)
             for num, ent, n in grouped.filter(
                 pl.col("season_start") == s0)
             .select("number", "entries", "n").iter_rows()}
        counts = [g.get(i, (0, []))[0] for i in range(100)]
        wearers = [g.get(i, (0, []))[1] for i in range(100)]
        data.append({"c": counts, "w": wearers})

    payload = json.dumps({"labels": labels, "data": data,
                          "maxList": WEARER_LIST_MAX})
    html = FIG6_TEMPLATE.replace("__PAYLOAD__", payload)
    (FIG / "fig6_number_histogram.html").write_text(html)


def main(argv: list[str]) -> int:
    df, notes = load_numbers()
    seasons = by_season(df)
    checks = gates(df, seasons, notes)

    if "--check" in argv:
        committed = pl.read_csv(OUT / "number_by_season.csv")
        drift = (seasons.sort("season_start")["median_number"]
                 - committed.sort("season_start")["median_number"]
                 ).abs().max()
        ok = bool(checks["passed"].all()) and float(drift) < 1e-9
        print("NUMBER EXPLORER CHECK "
              + ("PASSED" if ok else "FAILED")
              + f" ({checks.height} gates; committed medians reproduce, "
                f"max drift {float(drift):.2e})")
        return 0 if ok else 1

    seasons.drop("season").write_csv(OUT / "number_by_season.csv")
    checks.write_csv(OUT / "number_explorer_validation.csv")
    print(f"parsing notes: {notes}")
    with pl.Config(tbl_rows=-1, fmt_str_lengths=60):
        print(seasons.select("season", "n", "median_number", "share_0_00"))
        print(checks)
    figures(df, seasons)

    ok = bool(checks["passed"].all())
    print("NUMBER EXPLORER VALIDATION " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
