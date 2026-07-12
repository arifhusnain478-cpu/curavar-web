"""HTML triage dashboard: a curator's prioritized worklist across many variants."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .acmg import Classification
from .triage import TriageItem, summary_counts

_TIER_VAR = {
    Classification.BENIGN: "benign", Classification.LIKELY_BENIGN: "lbenign",
    Classification.VUS: "vus", Classification.LIKELY_PATHOGENIC: "lpath",
    Classification.PATHOGENIC: "path",
}
_BUCKET_CLS = {"ACT": "act", "REVIEW": "review", "CLEAR": "clear"}


def _e(s):
    return html.escape(str(s), quote=True)


def render_triage(items: list[TriageItem], tool_version: str = "0.1.0") -> str:
    counts = summary_counts(items)
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = []
    for it in items:
        rows.append(
            f'<tr class="row--{_BUCKET_CLS[it.bucket]}">'
            f'<td><span class="badge badge--{_BUCKET_CLS[it.bucket]}">{_e(it.bucket)}</span></td>'
            f'<td class="mono variant">{_e(it.variant)}</td>'
            f'<td><span class="tierchip v-{_TIER_VAR[it.headline]}">{_e(it.headline.value)}</span></td>'
            f'<td class="mono pts">{it.points:+d}</td>'
            f'<td class="reason">{_e(it.reason)}</td>'
            f'</tr>'
        )
    rows_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CuraVar triage worklist</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink:#111820; --ink-soft:#4b5763; --line:#d7dde2; --line-soft:#e7ebee;
    --paper:#f4f6f8; --card:#fff; --spine:#0f5b6b; --spine-deep:#0a3f4a;
    --path:#b3261e; --lpath:#c1631c; --vus:#6b7280; --lbenign:#2f8f79; --benign:#1f7a4d;
    --act:#c1631c; --review:#0f5b6b; --clear:#1f7a4d;
    --mono:'IBM Plex Mono',ui-monospace,monospace; --sans:'IBM Plex Sans',system-ui,sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans); }}
  .wrap {{ max-width:940px; margin:0 auto; padding:40px 24px 80px; }}
  .eyebrow {{ font-family:var(--mono); font-size:11px; letter-spacing:.14em; text-transform:uppercase;
             color:var(--spine); font-weight:600; }}
  h1 {{ font-size:26px; margin:6px 0 2px; letter-spacing:-.01em; }}
  .sub {{ font-family:var(--mono); font-size:12px; color:var(--ink-soft); margin-bottom:26px; }}
  .cards {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:30px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px;
          border-top:3px solid var(--line); }}
  .stat--act {{ border-top-color:var(--act); }}
  .stat--review {{ border-top-color:var(--review); }}
  .stat--clear {{ border-top-color:var(--clear); }}
  .stat .n {{ font-size:34px; font-weight:700; line-height:1; }}
  .stat .lbl {{ font-family:var(--mono); font-size:11px; letter-spacing:.08em; text-transform:uppercase;
               color:var(--ink-soft); margin-top:8px; }}
  .stat .desc {{ font-size:12.5px; color:var(--ink-soft); margin-top:6px; }}
  .ledger-wrap {{ border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--card); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase;
       color:var(--ink-soft); padding:11px 14px; border-bottom:1px solid var(--line); background:#fafbfc; }}
  td {{ padding:12px 14px; border-bottom:1px solid var(--line-soft); vertical-align:middle; }}
  tr:last-child td {{ border-bottom:none; }}
  .mono {{ font-family:var(--mono); }}
  .variant {{ font-weight:500; }}
  .badge {{ font-family:var(--mono); font-size:10px; font-weight:600; letter-spacing:.06em;
           padding:4px 8px; border-radius:5px; color:#fff; }}
  .badge--act {{ background:var(--act); }} .badge--review {{ background:var(--review); }}
  .badge--clear {{ background:var(--clear); }}
  .tierchip {{ font-size:12px; font-weight:600; }}
  .v-path {{ color:var(--path); }} .v-lpath {{ color:var(--lpath); }} .v-vus {{ color:var(--vus); }}
  .v-lbenign {{ color:var(--lbenign); }} .v-benign {{ color:var(--benign); }}
  .pts {{ color:var(--ink-soft); }} .reason {{ color:var(--ink-soft); font-size:12.5px; }}
  .row--review {{ background:#fcfaf5; }}
  .foot {{ margin-top:24px; font-family:var(--mono); font-size:11px; color:var(--ink-soft); }}
</style></head>
<body><div class="wrap">
  <div class="eyebrow">CuraVar · Triage worklist</div>
  <h1>{len(items)} variants triaged</h1>
  <div class="sub">Generated {_e(generated)} · sorted by how much they need a human · v{_e(tool_version)}</div>

  <div class="cards">
    <div class="stat stat--review"><div class="n">{counts['REVIEW']}</div>
      <div class="lbl">Needs review</div>
      <div class="desc">Conflicts, method divergence, or uncertain near a boundary.</div></div>
    <div class="stat stat--act"><div class="n">{counts['ACT']}</div>
      <div class="lbl">Actionable</div>
      <div class="desc">Reaches a (likely) pathogenic call — report out.</div></div>
    <div class="stat stat--clear"><div class="n">{counts['CLEAR']}</div>
      <div class="lbl">Auto-clear</div>
      <div class="desc">(Likely) benign — low priority.</div></div>
  </div>

  <div class="ledger-wrap"><table>
    <thead><tr><th>Queue</th><th>Variant</th><th>Classification</th><th>Points</th><th>Why</th></tr></thead>
    <tbody>
    {rows_html}
    </tbody>
  </table></div>

  <div class="foot">Each row links to a full auditable report with evidence, criteria, and a verifiable ledger.</div>
</div></body></html>"""
