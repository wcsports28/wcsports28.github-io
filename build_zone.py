#!/usr/bin/env python3
"""
WCS Analytics — builds tonight's NHL Line Zone page, fully automatic.

  1. Tonight's games + starting goalies ........ Daily Faceoff starting-goalies page
  2. Goalie Sv% / GSAx vs LW, RW, C, D ......... MoneyPuck shot data
  3. Each team's top 4 forward lines (5v5) ...... MoneyPuck line data, current season
     (falls back to last season if the current file isn't posted yet)
  4. Injects everything into template.html -> docs/index.html (served by GitHub Pages)

The page's own model (Scoring Index, tiers, Top 3, goalie scouting notes) runs in the browser.

Usage:  pip install requests pandas beautifulsoup4
        python build_zone.py                    # tonight (ET)
        python build_zone.py --date 2026-10-08
Data credit: MoneyPuck.com (credit required) and Daily Faceoff.
"""
import argparse, datetime as dt, io, json, re, sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from wcs_goalie_update import UA, TEAMS, load_shots, splits, norm, STATUSES
from bs4 import BeautifulSoup

LINES_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{season}/regular/lines.csv"
DFO_URL = "https://www.dailyfaceoff.com/starting-goalies/{date}"
CUR_SEASON = 2026      # MoneyPuck label = season start year (2026 = 2026-27)
MIN_TOI_MIN = 5        # ignore lines with < 5 min together

# workbook/page team name -> MoneyPuck team codes (old dotted codes included just in case)
CODES = {"Ducks": ["ANA"], "Bruins": ["BOS"], "Sabres": ["BUF"], "Flames": ["CGY"], "Hurricanes": ["CAR"],
 "Blackhawks": ["CHI"], "Avalanche": ["COL"], "Blue Jackets": ["CBJ"], "Stars": ["DAL"], "Red Wings": ["DET"],
 "Oilers": ["EDM"], "Panthers": ["FLA"], "Kings": ["LAK", "L.A"], "Wild": ["MIN"], "Canadiens": ["MTL"],
 "Predators": ["NSH"], "Devils": ["NJD", "N.J"], "Islanders": ["NYI"], "Rangers": ["NYR"], "Senators": ["OTT"],
 "Flyers": ["PHI"], "Penguins": ["PIT"], "Sharks": ["SJS", "S.J"], "Kraken": ["SEA"], "Blues": ["STL"],
 "Lightning": ["TBL", "T.B"], "Maple Leafs": ["TOR"], "Mammoth": ["UTA"], "Canucks": ["VAN"],
 "Golden Knights": ["VGK"], "Capitals": ["WSH"], "Jets": ["WPG"]}


def get_slate(date):
    html = requests.get(DFO_URL.format(date=date), headers=UA, timeout=30)
    html.raise_for_status()
    return parse_slate(html.text)


def parse_slate(html):
    """Return (games, starters). Games are kept even when goalies aren't posted yet."""
    lines = [l.strip() for l in BeautifulSoup(html, "html.parser").get_text("\n").split("\n") if l.strip()]
    games, cur = [], None
    for i, line in enumerate(lines):
        m = re.fullmatch(r"(.+?) at (.+)", line)
        if m and m.group(1) in TEAMS and m.group(2) in TEAMS:
            cur = {"away": TEAMS[m.group(1)], "home": TEAMS[m.group(2)], "g": []}
            games.append(cur)
        elif cur is not None and line in STATUSES and len(cur["g"]) < 2:
            cur["g"].append((lines[i - 1], line))
    starters = []
    for g in games:
        for (name, status), team, opp in zip(g["g"], (g["away"], g["home"]), (g["home"], g["away"])):
            starters.append({"team": team, "goalie": name, "status": status, "opp": opp})
    if not games:
        sys.exit("ERROR: no games found on Daily Faceoff for this date (off day, or the page layout changed).")
    return games, starters


def load_lines(local=None):
    for season in (CUR_SEASON, CUR_SEASON - 1):
        try:
            if local:
                df = pd.read_csv(local); season = "local file"
            else:
                r = requests.get(LINES_URL.format(season=season), headers=UA, timeout=60)
                r.raise_for_status(); df = pd.read_csv(io.StringIO(r.text))
            need = {"name", "team", "position", "situation", "icetime", "games_played", "shotAttemptsFor", "goalsFor",
                    "xGoalsFor", "highDangerShotsFor", "mediumDangerShotsFor", "shotAttemptsAgainst", "goalsAgainst",
                    "xGoalsAgainst", "highDangerShotsAgainst", "mediumDangerShotsAgainst"}
            miss = need - set(df.columns)
            if miss:
                sys.exit(f"ERROR: MoneyPuck lines file missing columns {sorted(miss)}")
            df = df[(df["position"] == "line") & (df["situation"] == "5on5") & (df["icetime"] >= MIN_TOI_MIN * 60)]
            if len(df):
                print(f"  MoneyPuck lines: season {season}, {len(df)} forward lines")
                return df, season
        except requests.RequestException as e:
            print(f"  ! lines season {season}: {e}")
        if local:
            break
    sys.exit("ERROR: no MoneyPuck line data available.")


def build_lines(df, games):
    opp = {}
    for g in games:
        opp[g["away"]] = g["home"]; opp[g["home"]] = g["away"]
    out = []
    for team in opp:  # keeps Daily Faceoff game order
        t = df[df["team"].isin(CODES.get(team, []))].sort_values("icetime", ascending=False).head(4)
        if t.empty:
            print(f"  ! no line data for {team}")
        for k, (_, r) in enumerate(t.iterrows(), 1):
            per60 = lambda v: round(float(r[v]) / r["icetime"] * 3600, 1)
            sc_for = (float(r["highDangerShotsFor"]) + float(r["mediumDangerShotsFor"])) / r["icetime"] * 3600
            sc_ag = (float(r["highDangerShotsAgainst"]) + float(r["mediumDangerShotsAgainst"])) / r["icetime"] * 3600
            cf, ca, xf, xa = (float(r[c]) for c in ("shotAttemptsFor", "shotAttemptsAgainst", "xGoalsFor", "xGoalsAgainst"))
            out.append({"team": team, "opp": opp[team], "line": f"FL{k}", "names": str(r["name"]).replace("-", " – "),
                        "toi": round(r["icetime"] / max(r["games_played"], 1) / 60, 1),
                        "cf60": per60("shotAttemptsFor"), "gf60": per60("goalsFor"), "xgf60": round(xf / r["icetime"] * 3600, 1),
                        "scf60": round(sc_for, 1), "hdcf60": per60("highDangerShotsFor"),
                        "ca60": per60("shotAttemptsAgainst"), "ga60": per60("goalsAgainst"), "xga60": round(xa / r["icetime"] * 3600, 1),
                        "sca60": round(sc_ag, 1), "hdca60": per60("highDangerShotsAgainst"),
                        "cfp": round(cf / (cf + ca), 3) if cf + ca else 0.5, "xgfp": round(xf / (xf + xa), 3) if xf + xa else 0.5})
    # WCS O-Score / D-Score: average percentile rank vs tonight's slate (0-100), like Daily Faceoff's slate-relative scores
    if out:
        f = pd.DataFrame(out)
        pr = lambda c, asc=True: f[c].rank(pct=True, ascending=asc)
        f["oscore"] = ((pr("cf60") + pr("gf60") + pr("xgf60") + pr("scf60") + pr("hdcf60")) / 5 * 100).round(1)
        f["dscore"] = ((pr("ca60", False) + pr("ga60", False) + pr("xga60", False) + pr("sca60", False) + pr("hdca60", False)) / 5 * 100).round(1)
        out = f.to_dict("records")
    return out


def goalie_rows(starters, shots):
    rows = []
    for s in starters:
        g = {**s, "sog": None, "minsog": None, "LW": [None, None], "RW": [None, None], "C": [None, None], "D": [None, None], "OV": [None, None]}
        sp = splits(shots, s["goalie"]) if shots is not None else None
        if sp:
            g.update({"sog": sp["total_sog"], "minsog": sp["min_sog"], "OV": list(sp["overall"]),
                      **{p: list(sp[p]) for p in ("LW", "RW", "C", "D")}})
        else:
            print(f"  ! no shot history for {s['goalie']}")
        rows.append(g)
    return rows


def clean(o):
    if isinstance(o, float) and o != o:
        return None
    if hasattr(o, "item"):
        return o.item()
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d"))
    ap.add_argument("--template", default="template.html")
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument("--cache", default=".mp_cache")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--html", help="saved Daily Faceoff page (testing)")
    ap.add_argument("--lines-csv", help="local MoneyPuck lines.csv (testing)")
    a = ap.parse_args()
    print(f"WCS Line Zone build for {a.date}")
    games, starters = parse_slate(Path(a.html).read_text()) if a.html else get_slate(a.date)
    print(f"  {len(games)} games, {len(starters)} starters listed")
    df, season = load_lines(a.lines_csv)
    lines = build_lines(df, games)
    shots = load_shots(Path(a.cache), a.offline)
    data = {"date": a.date, "lines": lines, "goalies": goalie_rows(starters, shots),
            "source": f"MoneyPuck.com 5v5 line data ({season} season, top 4 lines by TOI) — starters via Daily Faceoff; updated "
                      + dt.datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %I:%M %p ET")}
    payload = json.dumps(data, separators=(",", ":"), default=clean, allow_nan=False)
    tpl = Path(a.template).read_text(encoding="utf-8")
    new, n = re.subn(r"/\*WCS_DATA\*/.*?/\*END_WCS_DATA\*/", lambda _: "/*WCS_DATA*/" + payload + "/*END_WCS_DATA*/", tpl, flags=re.S)
    if n != 1:
        sys.exit("ERROR: data marker not found in template.html")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(new, encoding="utf-8")
    print(f"  wrote {a.out}: {len(lines)} lines, {len(data['goalies'])} goalies")


if __name__ == "__main__":
    main()
