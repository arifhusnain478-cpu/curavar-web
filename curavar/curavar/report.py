"""
Auditable HTML report generator.

Renders a CuraVarResult as a self-contained clinical-style report: the verdict,
a five-tier classification gauge, each activated ACMG criterion traced to the
evidence that justifies it, the reviewer's pruning decisions, and the full
provenance ledger with its hash chain and verification status.

Design intent: a clinical instrument readout, not a marketing page. Mono type
carries all coordinates/accessions/hashes; color encodes the five ACMG tiers.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .acmg import CRITERIA, Classification, Direction, Strength
from .pipeline import CuraVarResult

_TIER_ORDER = [
    Classification.BENIGN,
    Classification.LIKELY_BENIGN,
    Classification.VUS,
    Classification.LIKELY_PATHOGENIC,
    Classification.PATHOGENIC,
]
_TIER_SHORT = {
    Classification.BENIGN: "Benign",
    Classification.LIKELY_BENIGN: "Likely benign",
    Classification.VUS: "Uncertain (VUS)",
    Classification.LIKELY_PATHOGENIC: "Likely pathogenic",
    Classification.PATHOGENIC: "Pathogenic",
}
_TIER_VAR = {
    Classification.BENIGN: "benign",
    Classification.LIKELY_BENIGN: "lbenign",
    Classification.VUS: "vus",
    Classification.LIKELY_PATHOGENIC: "lpath",
    Classification.PATHOGENIC: "path",
}
_STRENGTH_LABEL = {
    Strength.VERY_STRONG: "Very strong",
    Strength.STRONG: "Strong",
    Strength.MODERATE: "Moderate",
    Strength.SUPPORTING: "Supporting",
    Strength.STANDALONE: "Standalone",
}


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_report(result: CuraVarResult, tool_version: str = "0.1.0") -> str:
    v = result.variant
    cls = result.classification
    pts = result.points
    rec = result.reconciled
    tier = rec.headline
    ledger_ok, ledger_problems = result.ledger.verify()

    # --- verdict gauge ---
    gauge_cells = []
    for t in _TIER_ORDER:
        active = " active" if t == tier else ""
        gauge_cells.append(
            f'<div class="tier tier--{_TIER_VAR[t]}{active}">'
            f'<span class="tier-dot"></span>{_e(_TIER_SHORT[t])}</div>'
        )
    gauge = "\n".join(gauge_cells)

    # --- evidence lookup ---
    by_id = {e.id: e for e in result.ledger.all()}

    def evidence_block(eids):
        rows = []
        for eid in eids:
            e = by_id.get(eid)
            if not e:
                rows.append(f'<div class="ev-miss">{_e(eid)} (not found)</div>')
                continue
            rows.append(
                f'<div class="ev">'
                f'<div class="ev-head"><span class="ev-id">{_e(e.id)}</span>'
                f'<span class="ev-src">{_e(e.source_name)}</span>'
                f'<span class="ev-loc">{_e(e.locator)}</span></div>'
                f'<div class="ev-snip">{_e(e.snippet)}</div>'
                f'</div>'
            )
        return "\n".join(rows)

    # --- criterion cards ---
    from .acmg import points_for
    cards = []
    for c in result.activated:
        direction, _, desc = CRITERIA[c.code]
        dir_cls = "path" if direction == Direction.PATHOGENIC else "benign"
        pv = points_for(c)
        cards.append(
            f'<article class="crit crit--{dir_cls}">'
            f'<header class="crit-head">'
            f'<span class="crit-code">{_e(c.code)}</span>'
            f'<span class="crit-strength">{_e(_STRENGTH_LABEL[c.strength])} '
            f'· {"Pathogenic" if direction==Direction.PATHOGENIC else "Benign"}</span>'
            f'<span class="crit-pts">{pv:+d} pt{"s" if abs(pv)!=1 else ""}</span>'
            f'</header>'
            f'<p class="crit-desc">{_e(desc)}</p>'
            f'<p class="crit-just"><span class="lbl">Why it applies</span>{_e(c.justification)}</p>'
            f'<div class="crit-ev"><span class="lbl">Traced to evidence</span>{evidence_block(c.evidence_ids)}</div>'
            f'</article>'
        )
    cards_html = "\n".join(cards) or '<p class="empty">No criteria met the evidentiary bar.</p>'

    # --- PVS1 decision-tree panel (if the tree ran) ---
    pvs1_html = ""
    for e in result.ledger.all():
        if e.source_name == "CuraVar PVS1 decision tree":
            steps = e.payload.get("path", [])
            strength = e.payload.get("strength", "")
            items = "\n".join(f'<li>{_e(s)}</li>' for s in steps)
            pvs1_html = (
                f'<section class="panel"><h2>PVS1 decision tree</h2>'
                f'<p class="panel-sub">Loss-of-function strength assigned by the '
                f'ClinGen SVI decision tree (Abou Tayoun et al. 2018), not by a '
                f'flat rule. Outcome: <b>{_e(strength)}</b>.</p>'
                f'<ol class="pvs1-steps">{items}</ol></section>'
            )

    # --- reviewer (adjudicator) removed list, pulled from the ledger ---
    removed_html = ""
    for e in result.ledger.all():
        if e.source_name == "CuraVar adjudicator":
            removed = e.payload.get("removed", [])
            if removed:
                items = "\n".join(
                    f'<li><span class="crit-code sm">{_e(r.get("code"))}</span>'
                    f'{_e(r.get("reason",""))}</li>'
                    for r in removed
                )
                removed_html = (
                    f'<section class="panel"><h2>Reviewer removed</h2>'
                    f'<p class="panel-sub">Proposed by the evidence pass but dropped for '
                    f'insufficient support. Removing weak claims is part of the audit trail.</p>'
                    f'<ul class="removed">{items}</ul></section>'
                )

    # --- ledger table ---
    ledger_rows = []
    for e in result.ledger.all():
        short_hash = e.entry_hash[:12]
        prev_short = (e.prev_hash[:12] if e.prev_hash else "—")
        ledger_rows.append(
            f'<tr>'
            f'<td class="mono">{_e(e.id)}</td>'
            f'<td>{_e(e.source_type.value)}</td>'
            f'<td>{_e(e.source_name)}</td>'
            f'<td class="mono">{_e(e.locator)}</td>'
            f'<td class="mono chain" title="{_e(e.entry_hash)}">'
            f'<span class="lnk">{_e(prev_short)}</span>→<span class="cur">{_e(short_hash)}</span></td>'
            f'</tr>'
        )
    ledger_html = "\n".join(ledger_rows)

    verify_cls = "ok" if ledger_ok else "bad"
    verify_txt = ("Chain verified — every entry hashes correctly and links to the previous one."
                  if ledger_ok else "Chain FAILED: " + "; ".join(ledger_problems))

    # --- method cross-check banner ---
    if rec.agree:
        xcheck = (f'<div class="banner banner--ok"><strong>Methods agree.</strong> '
                  f'Both the 2015 combining rules and the 2018/2020 points system '
                  f'return <b>{_e(cls.classification.value)}</b>.</div>')
    else:
        xcheck = (f'<div class="banner banner--warn"><strong>Methods diverge — expert review flagged.</strong> '
                  f'2015 rules: <b>{_e(cls.classification.value)}</b>; '
                  f'points system: <b>{_e(pts.classification.value)}</b> ({pts.score:+d} pts). '
                  f'{_e(rec.note)}</div>')

    # --- points scorebar (-10 .. +12 window) ---
    lo, hi = -10, 12
    frac = (max(lo, min(hi, pts.score)) - lo) / (hi - lo) * 100
    def _mark(x): return (x - lo) / (hi - lo) * 100
    scorebar = (
        f'<div class="scorebar">'
        f'<div class="sb-track">'
        f'<span class="sb-zone" style="left:0;width:{_mark(-6):.1f}%;background:var(--benign)"></span>'
        f'<span class="sb-zone" style="left:{_mark(-6):.1f}%;width:{_mark(-1)-_mark(-6):.1f}%;background:var(--lbenign)"></span>'
        f'<span class="sb-zone" style="left:{_mark(0):.1f}%;width:{_mark(5)-_mark(0):.1f}%;background:var(--vus)"></span>'
        f'<span class="sb-zone" style="left:{_mark(6):.1f}%;width:{_mark(9)-_mark(6):.1f}%;background:var(--lpath)"></span>'
        f'<span class="sb-zone" style="left:{_mark(10):.1f}%;width:{100-_mark(10):.1f}%;background:var(--path)"></span>'
        f'<span class="sb-needle" style="left:{frac:.1f}%"></span>'
        f'</div>'
        f'<div class="sb-labels"><span>Benign −6</span><span>VUS 0–5</span>'
        f'<span>Path ≥10</span></div>'
        f'<div class="sb-caption">Points score <b>{pts.score:+d}</b> '
        f'({pts.pathogenic_points:+d} pathogenic, {pts.benign_points:+d} benign)'
        f'{" · " + _e(pts.distance_to_next) if pts.distance_to_next else ""}</div>'
        f'</div>'
    )

    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CuraVar report · {_e(v.gene)} {_e(v.hgvs_c)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink:#111820; --ink-soft:#4b5763; --line:#d7ddE2; --line-soft:#e7ebee;
    --paper:#f4f6f8; --card:#ffffff; --spine:#0f5b6b; --spine-deep:#0a3f4a;
    --path:#b3261e; --lpath:#c1631c; --vus:#6b7280; --lbenign:#2f8f79; --benign:#1f7a4d;
    --mono:'IBM Plex Mono',ui-monospace,monospace; --sans:'IBM Plex Sans',system-ui,sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans);
         line-height:1.5; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:940px; margin:0 auto; padding:40px 24px 80px; }}
  a {{ color:var(--spine); }}

  /* header */
  .rpt-head {{ border-top:3px solid var(--spine); padding-top:18px;
              display:flex; justify-content:space-between; align-items:flex-start; gap:24px;
              flex-wrap:wrap; }}
  .eyebrow {{ font-family:var(--mono); font-size:11px; letter-spacing:.14em; text-transform:uppercase;
             color:var(--spine); font-weight:600; }}
  .variant {{ font-family:var(--mono); font-size:30px; font-weight:600; margin:6px 0 2px;
             letter-spacing:-.01em; }}
  .subvar {{ font-family:var(--mono); font-size:13px; color:var(--ink-soft); }}
  .meta {{ font-family:var(--mono); font-size:11px; color:var(--ink-soft); text-align:right;
          line-height:1.8; }}
  .meta b {{ color:var(--ink); font-weight:600; }}

  /* verdict */
  .verdict {{ margin:26px 0 8px; background:var(--card); border:1px solid var(--line);
             border-radius:10px; overflow:hidden; }}
  .verdict-top {{ padding:20px 22px; display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
                 border-bottom:1px solid var(--line-soft); }}
  .verdict-label {{ font-family:var(--mono); font-size:11px; letter-spacing:.12em;
                   text-transform:uppercase; color:var(--ink-soft); }}
  .verdict-value {{ font-size:26px; font-weight:700; letter-spacing:-.01em; }}
  .v-path {{ color:var(--path); }} .v-lpath {{ color:var(--lpath); }}
  .v-vus {{ color:var(--vus); }} .v-lbenign {{ color:var(--lbenign); }}
  .v-benign {{ color:var(--benign); }}
  .rule {{ font-family:var(--mono); font-size:12px; color:var(--ink-soft); margin-left:auto; }}

  /* gauge */
  .gauge {{ display:grid; grid-template-columns:repeat(5,1fr); }}
  .tier {{ font-family:var(--mono); font-size:11px; text-align:center; padding:12px 6px;
          color:var(--ink-soft); border-right:1px solid var(--line-soft); position:relative;
          display:flex; flex-direction:column; align-items:center; gap:7px; }}
  .tier:last-child {{ border-right:none; }}
  .tier-dot {{ width:9px; height:9px; border-radius:50%; background:var(--line);
              border:2px solid var(--line); }}
  .tier--benign .tier-dot {{ background:transparent; border-color:var(--benign); }}
  .tier--lbenign .tier-dot {{ background:transparent; border-color:var(--lbenign); }}
  .tier--vus .tier-dot {{ background:transparent; border-color:var(--vus); }}
  .tier--lpath .tier-dot {{ background:transparent; border-color:var(--lpath); }}
  .tier--path .tier-dot {{ background:transparent; border-color:var(--path); }}
  .tier.active {{ color:var(--ink); font-weight:600; background:#fbfcfd; }}
  .tier--benign.active {{ box-shadow:inset 0 -3px 0 var(--benign); }}
  .tier--benign.active .tier-dot {{ background:var(--benign); }}
  .tier--lbenign.active {{ box-shadow:inset 0 -3px 0 var(--lbenign); }}
  .tier--lbenign.active .tier-dot {{ background:var(--lbenign); }}
  .tier--vus.active {{ box-shadow:inset 0 -3px 0 var(--vus); }}
  .tier--vus.active .tier-dot {{ background:var(--vus); }}
  .tier--lpath.active {{ box-shadow:inset 0 -3px 0 var(--lpath); }}
  .tier--lpath.active .tier-dot {{ background:var(--lpath); }}
  .tier--path.active {{ box-shadow:inset 0 -3px 0 var(--path); }}
  .tier--path.active .tier-dot {{ background:var(--path); }}

  .banner {{ margin:16px 0; padding:12px 16px; border-radius:8px; font-size:13.5px; }}
  .banner--warn {{ background:#fbf3e6; border:1px solid #e6cf9c; color:#7a4e12; }}
  .banner--ok {{ background:#eaf6ef; border:1px solid #b7e0c6; color:#1f6d44; }}

  /* points scorebar */
  .scorebar {{ padding:16px 22px 20px; border-top:1px solid var(--line-soft); }}
  .sb-track {{ position:relative; height:12px; border-radius:6px; overflow:hidden;
              background:var(--line-soft); }}
  .sb-zone {{ position:absolute; top:0; height:100%; opacity:.32; }}
  .sb-needle {{ position:absolute; top:-4px; width:2px; height:20px; background:var(--ink);
               transform:translateX(-1px); }}
  .sb-needle::after {{ content:""; position:absolute; top:-4px; left:-3px; width:8px; height:8px;
                      border-radius:50%; background:var(--ink); }}
  .sb-labels {{ display:flex; justify-content:space-between; font-family:var(--mono);
               font-size:10px; color:var(--ink-soft); margin-top:9px; }}
  .sb-caption {{ font-family:var(--mono); font-size:12px; color:var(--ink-soft); margin-top:8px; }}
  .sb-caption b {{ color:var(--ink); }}
  .crit-pts {{ margin-left:auto; font-family:var(--mono); font-size:12px; font-weight:600;
              color:var(--spine-deep); }}

  h2 {{ font-size:13px; font-family:var(--mono); letter-spacing:.1em; text-transform:uppercase;
       color:var(--spine-deep); margin:38px 0 4px; }}
  .panel-sub, .sect-sub {{ color:var(--ink-soft); font-size:13px; margin:0 0 14px; }}

  /* criteria */
  .crit {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--line);
          border-radius:8px; padding:16px 18px; margin-bottom:12px; }}
  .crit--path {{ border-left-color:var(--path); }}
  .crit--benign {{ border-left-color:var(--benign); }}
  .crit-head {{ display:flex; align-items:baseline; gap:12px; }}
  .crit-code {{ font-family:var(--mono); font-weight:600; font-size:17px; }}
  .crit-code.sm {{ font-size:13px; margin-right:8px; }}
  .crit-strength {{ font-family:var(--mono); font-size:11px; color:var(--ink-soft);
                   letter-spacing:.04em; }}
  .crit-desc {{ font-size:13.5px; color:var(--ink-soft); margin:8px 0 12px; }}
  .lbl {{ display:block; font-family:var(--mono); font-size:10px; letter-spacing:.12em;
         text-transform:uppercase; color:var(--spine); margin-bottom:4px; }}
  .crit-just {{ font-size:14px; margin:0 0 12px; }}
  .ev {{ border:1px solid var(--line-soft); border-radius:6px; padding:9px 11px; margin-top:7px;
        background:#fafbfc; }}
  .ev-head {{ display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; font-family:var(--mono);
             font-size:11px; }}
  .ev-id {{ font-weight:600; color:var(--spine); }}
  .ev-src {{ color:var(--ink); }} .ev-loc {{ color:var(--ink-soft); }}
  .ev-snip {{ font-size:13px; margin-top:5px; color:var(--ink); }}
  .ev-miss {{ font-family:var(--mono); font-size:12px; color:var(--path); }}

  .pvs1-steps {{ margin:0; padding-left:20px; font-size:13.5px; color:var(--ink); }}
  .pvs1-steps li {{ padding:4px 0; font-family:var(--mono); font-size:12.5px; }}
  .removed {{ list-style:none; padding:0; margin:0; }}
  .removed li {{ font-size:13.5px; padding:9px 0; border-bottom:1px solid var(--line-soft); }}
  .removed li:last-child {{ border-bottom:none; }}

  /* ledger */
  .ledger-wrap {{ border:1px solid var(--line); border-radius:8px; overflow:hidden;
                 background:var(--card); }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  th {{ text-align:left; font-family:var(--mono); font-size:10px; letter-spacing:.1em;
       text-transform:uppercase; color:var(--ink-soft); padding:10px 12px;
       border-bottom:1px solid var(--line); background:#fafbfc; }}
  td {{ padding:9px 12px; border-bottom:1px solid var(--line-soft); vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  .mono {{ font-family:var(--mono); }}
  .chain .lnk {{ color:var(--ink-soft); }} .chain .cur {{ color:var(--spine-deep); font-weight:600; }}

  .verify {{ margin-top:14px; padding:13px 16px; border-radius:8px; font-family:var(--mono);
            font-size:12.5px; display:flex; align-items:center; gap:10px; }}
  .verify.ok {{ background:#eaf6ef; border:1px solid #b7e0c6; color:#1f7a4d; }}
  .verify.bad {{ background:#fbecea; border:1px solid #edbcb6; color:var(--path); }}
  .verify .mark {{ font-weight:700; }}

  .disclaimer {{ margin-top:40px; padding-top:18px; border-top:1px solid var(--line);
                font-size:12px; color:var(--ink-soft); }}
  .disclaimer strong {{ color:var(--ink); }}
  .foot {{ margin-top:22px; font-family:var(--mono); font-size:11px; color:var(--ink-soft); }}
  @media (max-width:560px) {{
    .variant {{ font-size:23px; }} .meta {{ text-align:left; }}
    .tier {{ font-size:9.5px; }}
  }}
</style>
</head>
<body>
<div class="wrap">

  <header class="rpt-head">
    <div>
      <div class="eyebrow">CuraVar · Auditable variant curation</div>
      <div class="variant">{_e(v.gene)} {_e(v.hgvs_c)}</div>
      <div class="subvar">{_e(v.hgvs_p)} · {_e(v.genome_build)} · {_e(v.coordinate)}</div>
    </div>
    <div class="meta">
      <div>Inheritance <b>{_e(v.inheritance or "—")}</b></div>
      <div>Generated <b>{_e(generated)}</b></div>
      <div>Engine <b>ACMG/AMP 2015 + points 2018/2020</b> · v{_e(tool_version)}</div>
    </div>
  </header>

  <section class="verdict">
    <div class="verdict-top">
      <span class="verdict-label">Classification</span>
      <span class="verdict-value v-{_TIER_VAR[tier]}">{_e(tier.value)}</span>
      <span class="rule">reconciled from two methods</span>
    </div>
    <div class="gauge">
      {gauge}
    </div>
    {scorebar}
  </section>

  {xcheck}

  <h2>Evidence → criteria</h2>
  <p class="sect-sub">Each criterion below was proposed against the evidence and survived review.
     Every one is traced to the specific ledger entries that justify it.</p>
  {cards_html}

  {pvs1_html}

  {removed_html}

  <h2>Provenance ledger</h2>
  <p class="sect-sub">Every raw observation used in this decision, in the order it entered.
     Each entry is hash-chained to the one before it.</p>
  <div class="ledger-wrap">
    <table>
      <thead><tr><th>ID</th><th>Type</th><th>Source</th><th>Locator</th><th>Prev → entry hash</th></tr></thead>
      <tbody>
        {ledger_html}
      </tbody>
    </table>
  </div>
  <div class="verify {verify_cls}">
    <span class="mark">{"✓" if ledger_ok else "✕"}</span>
    <span>{_e(verify_txt)}</span>
  </div>

  <div class="disclaimer">
    <strong>Research decision-support only.</strong> CuraVar aggregates public evidence and
    applies the ACMG/AMP 2015 combining rules to make its reasoning inspectable. It does not
    provide a clinical diagnosis. A qualified molecular geneticist is responsible for the final
    interpretation. No patient-identifiable data is used; bundled demo evidence is a recorded snapshot.
  </div>
  <div class="foot">CuraVar v{_e(tool_version)} · classification math is deterministic and LLM-free ·
     ledger integrity is independently re-verifiable</div>

</div>
</body>
</html>"""
