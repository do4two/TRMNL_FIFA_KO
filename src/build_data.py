#!/usr/bin/env python3
"""
Fetch FIFA World Cup 2026 data (openfootball), build the knockout-bracket model,
and emit the JSON payload that the TRMNL bracket plugin consumes.

Usage:
  # write output/trmnl_data.json from the live openfootball feed
  python src/build_data.py

  # use a local cached copy instead of the network
  python src/build_data.py --matches data/worldcup.json --teams data/worldcup.teams.json

  # simulate a played-out bracket from a results overlay (see data/simulate_*.json)
  python src/build_data.py --simulate data/simulate_full.json

  # also POST it to a TRMNL private-plugin webhook (merge_variables)
  python src/build_data.py --webhook https://trmnl.com/api/custom_plugins/<uuid>

The output top-level keys become Liquid merge variables under the Polling
strategy (or are wrapped in {"merge_variables": ...} for the webhook strategy):

  {
    "updated_at": "2026-07-05 21:30 UTC",
    "tournament": "World Cup 2026",
    "ko_played": 5, "ko_total": 32,
    "champion": null | {"name","code","flag"},
    "left":  {"r32":[...8], "r16":[...4], "qf":[...2], "sf":[...1]},
    "right": {"r32":[...8], "r16":[...4], "qf":[...2], "sf":[...1]},
    "final": {match}, "third": {match}
  }
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import bracket as B

OPENFOOTBALL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026"
MATCHES_URL = OPENFOOTBALL + "/worldcup.json"
TEAMS_URL = OPENFOOTBALL + "/worldcup.teams.json"


def _fetch(url):
    """GET a URL via urllib, falling back to curl (some environments block
    Python's sockets but allow curl)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "trmnl-wm2026-ko"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        if shutil.which("curl"):
            out = subprocess.run(
                ["curl", "-sSL", "--fail", "--max-time", "30", url],
                capture_output=True, text=True,
            )
            if out.returncode == 0 and out.stdout:
                return out.stdout
        raise RuntimeError("could not fetch %s: %s" % (url, e))


def _load(path_or_url):
    if path_or_url.startswith(("http://", "https://")):
        return json.loads(_fetch(path_or_url))
    with open(path_or_url, encoding="utf-8") as f:
        return json.load(f)


def _apply_simulation(matches, overlay):
    """Overlay results onto matches for local previewing of a filled bracket.

    The overlay maps match `num` (as a string) to a result, e.g.
        {"73": {"team1": "Croatia", "team2": "Brazil", "ft": [1, 2]},
         "101": {"ft": [1, 1], "pen": [4, 2]}}
    Group matches may also be keyed by num to finalise group order."""
    by_num = {m.get("num"): m for m in matches if isinstance(m.get("num"), int)}
    for k, v in overlay.items():
        m = by_num.get(int(k))
        if m is None:
            continue
        if "team1" in v:
            m["team1"] = v["team1"]
        if "team2" in v:
            m["team2"] = v["team2"]
        sc = {}
        for key in ("ft", "ht", "et", "pen"):
            if key in v:
                sc[key] = v[key]
        if sc:
            m["score"] = sc
    return matches


def build_payload(matches_src, teams_src, simulate=None):
    matches_doc = _load(matches_src)
    teams = _load(teams_src)
    matches = matches_doc.get("matches", matches_doc) if isinstance(matches_doc, dict) else matches_doc

    if simulate:
        matches = _apply_simulation(matches, _load(simulate))

    payload = B.build_bracket(teams, matches)
    payload.update({
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tournament": matches_doc.get("name", "World Cup 2026")
        if isinstance(matches_doc, dict) else "World Cup 2026",
    })
    return payload


def post_webhook(url, payload):
    body = json.dumps({"merge_variables": payload}).encode("utf-8")
    size = len(body)
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Webhook %s -> HTTP %s (%d bytes sent)" % (url, r.status, size))
    if size > 2048:
        print("WARNING: payload is %d bytes; free TRMNL webhook limit is 2KB "
              "(5KB for TRMNL+). Prefer the Polling strategy." % size,
              file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matches", default=MATCHES_URL, help="path or URL to worldcup.json")
    ap.add_argument("--teams", default=TEAMS_URL, help="path or URL to worldcup.teams.json")
    ap.add_argument("--simulate", help="results-overlay JSON to fill the bracket (preview)")
    ap.add_argument("--out", default="output/trmnl_data.json", help="output JSON path")
    ap.add_argument("--webhook", help="TRMNL private-plugin webhook URL to POST to")
    args = ap.parse_args()

    payload = build_payload(args.matches, args.teams, args.simulate)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    champ = payload["champion"]["code"] if payload["champion"] else "—"
    print("Wrote %s  (%d/%d KO matches decided, champion: %s, %d bytes)"
          % (args.out, payload["ko_played"], payload["ko_total"], champ,
             len(json.dumps(payload, ensure_ascii=False))))

    if args.webhook:
        post_webhook(args.webhook, payload)


if __name__ == "__main__":
    main()
