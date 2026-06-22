"""
FIFA World Cup 2026 – knockout bracket model.

Pure functions (no I/O) so they are easy to unit-test. Mirrors the
openfootball/worldcup.json structure, where every knockout match is encoded as

  {"num": 89, "round": "Round of 16", "team1": "W74", "team2": "W77",
   "score": {"ft": [int, int], "et": [...], "pen": [...]}}

The interesting part is the *slot placeholders*. Before a pairing is known the
source carries symbolic references instead of team names:

  "1A" / "2B"        winner / runner-up of a group  (resolved once that group's
                     six matches are all played -> final table order is fixed)
  "3A/B/C/D/F"       one of the eight best third-placed teams (which group it is
                     only becomes known via FIFA's allocation table -> kept as a
                     placeholder until the source replaces it with a real name)
  "W74" / "L101"     winner / loser of match 74 / 101 (resolved once that match
                     is decided; in the meantime shown as "S.74" / "V.101")
  "Mexico"           a real team name (source has already filled the slot)

A knockout match is *decided* by full-time goals, else extra time ("n.V."),
else a penalty shoot-out ("i.E.") – draws are impossible at full time here.

The bracket *topology* is not hard-coded: it is rebuilt every run by following
the W*/L* references back from the Final (match 104). team1 always feeds the
upper half of the tree, team2 the lower half, so a post-order traversal yields
the matches of each round already ordered top-to-bottom – exactly what the
"meeting in the middle" layout needs.
"""

import re

import standings as S

# round label (openfootball) -> short key used in the payload / templates
ROUND_KEY = {
    "Round of 32": "r32",
    "Round of 16": "r16",
    "Quarter-final": "qf",
    "Semi-final": "sf",
    "Final": "final",
    "Match for third place": "third",
}
ROUND_LABEL = {
    "r32": "Achtelfinale",      # Round of 32 (Sechzehntelfinale is unusual in DE)
    "r16": "Achtelfinale",
    "qf": "Viertelfinale",
    "sf": "Halbfinale",
    "final": "Finale",
    "third": "Spiel um Platz 3",
}
# proper German names (R32 = "Sechzehntelfinale", R16 = "Achtelfinale")
ROUND_LABEL["r32"] = "Sechzehntelfinale"

_SLOT_GROUP = re.compile(r"^([123])([A-L])$")        # 1A / 2B / 3C
_SLOT_MATCH = re.compile(r"^([WL])(\d+)$")           # W74 / L101


def knockout_matches(matches):
    """All matches that belong to the knockout phase, keyed by `num`."""
    ko = {}
    for m in matches:
        if m.get("round") in ROUND_KEY and isinstance(m.get("num"), int):
            ko[m["num"]] = m
    return ko


# --------------------------------------------------------------------------- #
# result / outcome of a single match
# --------------------------------------------------------------------------- #
def outcome(match):
    """Return {"win": 0|1, "note": ""|"n.V."|"i.E."} or None if not decided.

    win is the index (0 = team1, 1 = team2) of the winner. A knockout tie is
    broken by extra time (et) then penalties (pen)."""
    sc = match.get("score") or {}
    ft = sc.get("ft")
    if not (isinstance(ft, (list, tuple)) and len(ft) == 2
            and all(isinstance(x, int) for x in ft)):
        return None
    et, pen = sc.get("et"), sc.get("pen")
    if ft[0] != ft[1]:
        return {"win": 0 if ft[0] > ft[1] else 1, "note": ""}
    if isinstance(et, (list, tuple)) and len(et) == 2 and et[0] != et[1]:
        return {"win": 0 if et[0] > et[1] else 1, "note": "n.V."}
    if isinstance(pen, (list, tuple)) and len(pen) == 2 and pen[0] != pen[1]:
        return {"win": 0 if pen[0] > pen[1] else 1, "note": "i.E."}
    return None  # tie with no et/pen data -> treat as not yet decided


def _score_str(match):
    """Compact score string for display, e.g. "2:1" or "1:1 i.E."."""
    sc = match.get("score") or {}
    ft = sc.get("ft")
    if not (isinstance(ft, (list, tuple)) and len(ft) == 2):
        return ""
    base = "%d:%d" % (ft[0], ft[1])
    out = outcome(match)
    if out and out["note"]:
        return base + " " + out["note"]
    return base


# --------------------------------------------------------------------------- #
# group winner / runner-up resolution
# --------------------------------------------------------------------------- #
def _group_positions(teams, matches):
    """letter -> {1: rowdict, 2: rowdict} for mathematically fixed positions.

    Before a group is complete, only positions proven under every remaining
    W/D/L scenario are exposed. Once all games are played, the final table
    supplies positions 1 and 2 as before.
    """
    groups = S.build_standings(teams, matches)
    out = {}
    for g in groups:
        letter = g["name"]
        gms = S.group_matches(matches, letter)
        ordered = g["teams"]
        pos = {}
        if gms and all(S.is_played(m) for m in gms):
            if len(ordered) >= 1:
                pos[1] = ordered[0]
            if len(ordered) >= 2:
                pos[2] = ordered[1]
        else:
            for row in ordered:
                clinched = row.get("clinched_position")
                if clinched in (1, 2):
                    pos[clinched] = row
        if pos:
            out[letter] = pos
    return out


# --------------------------------------------------------------------------- #
# slot resolution
# --------------------------------------------------------------------------- #
def _team_obj(name, code, flag, resolved, placeholder):
    return {"name": name, "code": code, "flag": flag,
            "resolved": resolved, "placeholder": placeholder}


def resolve_slot(slot, ko, teams_by_name, group_pos, _seen=None):
    """Resolve one slot string to a team object (see module docstring).

    Falls back to a human placeholder ("1A", "S.74", "3.") when the team behind
    a slot is not yet determined. Recurses through W*/L* references."""
    _seen = _seen or set()
    slot = (slot or "").strip()

    # 1) already a real team name
    if slot in teams_by_name:
        t = teams_by_name[slot]
        return _team_obj(t["name"], t.get("fifa_code") or t["name"][:3].upper(),
                         t.get("flag_icon") or "", True, slot)

    # 2) winner / loser of another match
    mm = _SLOT_MATCH.match(slot)
    if mm:
        kind, num = mm.group(1), int(mm.group(2))
        ref = ko.get(num)
        if ref is not None and num not in _seen:
            out = outcome(ref)
            if out is not None:
                widx = out["win"] if kind == "W" else 1 - out["win"]
                src_slot = ref["team1"] if widx == 0 else ref["team2"]
                return resolve_slot(src_slot, ko, teams_by_name, group_pos,
                                    _seen | {num})
        label = ("S." if kind == "W" else "V.") + str(num)
        return _team_obj(label, label, "", False, label)

    # 3) group winner / runner-up / third
    gm = _SLOT_GROUP.match(slot)
    if gm:
        pos, letter = int(gm.group(1)), gm.group(2)
        if pos in (1, 2):
            row = group_pos.get(letter, {}).get(pos)
            if row:
                return _team_obj(row["name"], row["code"], row.get("flag", ""),
                                 True, slot)
            return _team_obj(slot, slot, "", False, slot)
        # third place: which group is unknown until the source fills it in
        return _team_obj(slot, "3.", "", False, slot)

    # 4) anything else (e.g. "3A/B/C/D/F") -> placeholder as-is
    short = "3." if slot.startswith("3") else slot
    return _team_obj(slot, short, "", False, short)


# --------------------------------------------------------------------------- #
# one match -> renderable dict
# --------------------------------------------------------------------------- #
def build_match(match, ko, teams_by_name, group_pos):
    out = outcome(match)
    t1 = resolve_slot(match["team1"], ko, teams_by_name, group_pos)
    t2 = resolve_slot(match["team2"], ko, teams_by_name, group_pos)
    sc = match.get("score") or {}
    ft = sc.get("ft") if isinstance(sc.get("ft"), (list, tuple)) else [None, None]
    t1 = dict(t1, score=ft[0] if out else None,
              winner=bool(out and out["win"] == 0),
              loser=bool(out and out["win"] == 1))
    t2 = dict(t2, score=ft[1] if out else None,
              winner=bool(out and out["win"] == 1),
              loser=bool(out and out["win"] == 0))
    return {
        "num": match["num"],
        "round": ROUND_KEY[match["round"]],
        "decided": out is not None,
        "note": out["note"] if out else "",
        "score_str": _score_str(match),
        "t1": t1, "t2": t2,
    }


# --------------------------------------------------------------------------- #
# topology: walk the tree back from a root match
# --------------------------------------------------------------------------- #
def _source_num(slot):
    """The match number feeding a W*/L* slot, else None (a group/leaf slot)."""
    mm = _SLOT_MATCH.match((slot or "").strip())
    return int(mm.group(2)) if mm else None


def collect_half(root_num, ko):
    """Post-order traversal from `root_num`; returns {round_key: [nums...]}
    with each round's matches ordered top-to-bottom."""
    cols = {}

    def walk(num):
        m = ko.get(num)
        if m is None:
            return
        walk(_source_num(m["team1"]))
        walk(_source_num(m["team2"]))
        cols.setdefault(ROUND_KEY[m["round"]], []).append(num)

    walk(root_num)
    return cols


# --------------------------------------------------------------------------- #
# top-level assembly
# --------------------------------------------------------------------------- #
def build_bracket(teams, matches):
    """Return the full bracket payload (see README for the shape)."""
    ko = knockout_matches(matches)
    teams_by_name = {t["name"]: t for t in teams}
    group_pos = _group_positions(teams, matches)

    def mk(num):
        return build_match(ko[num], ko, teams_by_name, group_pos)

    final = ko.get(104)
    # left half feeds Final.team1 (W101), right half feeds Final.team2 (W102)
    left_root = _source_num(final["team1"]) if final else None
    right_root = _source_num(final["team2"]) if final else None
    left_cols = collect_half(left_root, ko) if left_root else {}
    right_cols = collect_half(right_root, ko) if right_root else {}

    def side(cols):
        return {k: [mk(n) for n in cols.get(k, [])]
                for k in ("r32", "r16", "qf", "sf")}

    final_m = mk(104) if 104 in ko else None
    third_m = mk(103) if 103 in ko else None

    champion = None
    if final_m and final_m["decided"]:
        champ = final_m["t1"] if final_m["t1"]["winner"] else final_m["t2"]
        champion = {"name": champ["name"], "code": champ["code"],
                    "flag": champ["flag"]}

    played = sum(1 for n, m in ko.items() if outcome(m) is not None)

    return {
        "left": side(left_cols),
        "right": side(right_cols),
        "final": final_m,
        "third": third_m,
        "champion": champion,
        "ko_played": played,
        "ko_total": len(ko),
    }
