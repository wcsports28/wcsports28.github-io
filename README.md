# WCS NHL Line Zone — auto-updating page

Every day (Oct–Jun) at 3:45, 5:15 and 6:30 PM ET, GitHub Actions:
1. reads tonight's games + starting goalies from Daily Faceoff,
2. pulls MoneyPuck 5v5 line data (each team's top 4 forward lines by ice time) and shot data (goalie Sv% / GSAx vs LW, RW, C, D),
3. writes everything into `docs/index.html` and publishes it on GitHub Pages.

The page itself ranks the lines, picks the Top 3, and writes the goalie scouting notes.

## One-time setup (about 5 minutes)
1. Create a GitHub repo and upload everything in this folder (keep the `.github` and `docs` folders).
2. Settings → Actions → General → Workflow permissions → **Read and write** → Save.
3. Settings → Pages → Source: **Deploy from a branch** → Branch `main`, folder `/docs` → Save.
4. Actions tab → "WCS NHL Line Zone — daily build" → **Run workflow**. When it goes green, open
   `https://<your-username>.github.io/<repo-name>/`. Bookmark it — that link updates itself daily.

GitHub Pages is public on free plans; use a paid plan or another host if the page must stay private.

## Files
- `build_zone.py` — the daily build (run it locally with `python build_zone.py`)
- `wcs_goalie_update.py` — goalie helpers (also still fills the Excel Goalies tab if you use it)
- `template.html` — the page design; edit this, not `docs/index.html`
- `WCS_NHL_Line_Stats.xlsx` — the spreadsheet version

Data: MoneyPuck.com (credit required) and Daily Faceoff.
