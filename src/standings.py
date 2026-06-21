"""
FIFA World Cup 2026 – group standings + qualification logic.

Pure functions (no I/O) so they are easy to unit-test. The data shapes mirror
the openfootball/worldcup.json structure:

  team:  {"name","fifa_code","flag_icon","group", ...}
  match: {"team1","team2","group":"Group A","score":{"ft":[g1,g2]}, ...}

A match counts as *played* iff it has score.ft == [int, int].

Group order (FIFA tiebreakers, in this order):
  1) points  2) goal difference  3) goals for
  4) head-to-head among the still-tied teams (pts, gd, gf in their mutual games)
  5) fair play  6) drawing of lots
Fair play / lots data are not available in the source, so once 1–4 cannot
break a tie we fall back to alphabetical order (documented in the README).

"Safe qualification" / elimination is computed by brute force over every
possible win/draw/loss combination of the remaining group matches. This is
exact for *points* and uses the worst/best tiebreaker resolution so the answer
is always sound (never claims a guarantee that does not hold):

  * qualified_top2  -> in EVERY scenario the team is top-2 even if it loses all
                       point-ties (worst case). Top-2 always advance, so this is
                       a guarantee of advancing.  -> rendered BOLD.
  * group_winner    -> in EVERY scenario the team is 1st even in its worst tie
                       case.  -> rendered with a small marker.
  * eliminated      -> the team can NOT reach top-2 in any scenario AND its best
                       possible final points are below the guaranteed floor of
                       the 8th-best third-placed team across the other groups,
                       so it cannot sneak in as a best-third either.
                       -> rendered greyed / struck through.
"""

from itertools import product

GROUP_LETTERS = list("ABCDEFGHIJKL")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def group_letter(match):
    """'Group A' -> 'A'.  Returns None for non-group (knockout) matches."""
    g = match.get("group")
    if not g or not str(g).startswith("Group"):
        return None
    return str(g).split()[-1]


def is_played(match):
    ft = (match.get("score") or {}).get("ft")
    return (
        isinstance(ft, (list, tuple))
        and len(ft) == 2
        and all(isinstance(x, int) for x in ft)
    )


def group_matches(matches, letter):
    return [m for m in matches if group_letter(m) == letter]


def _blank_row(team):
    return {
        "name": team["name"],
        "code": team.get("fifa_code") or team["name"][:3].upper(),
        "flag": team.get("flag_icon") or "",
        "p": 0, "w": 0, "d": 0, "l": 0,
        "gf": 0, "ga": 0, "gd": 0, "pts": 0,
    }


# --------------------------------------------------------------------------- #
# table computation
# --------------------------------------------------------------------------- #
def compute_rows(team_names, teams_by_name, matches):
    """Return per-team aggregate stats (unsorted) for one group."""
    rows = {n: _blank_row(teams_by_name[n]) for n in team_names}
    for m in matches:
        if not is_played(m):
            continue
        t1, t2 = m["team1"], m["team2"]
        if t1 not in rows or t2 not in rows:
            continue  # defensive: ignore stray names
        g1, g2 = m["score"]["ft"]
        for t, gf, ga in ((t1, g1, g2), (t2, g2, g1)):
            r = rows[t]
            r["p"] += 1
            r["gf"] += gf
            r["ga"] += ga
            r["gd"] = r["gf"] - r["ga"]
            if gf > ga:
                r["w"] += 1; r["pts"] += 3
            elif gf == ga:
                r["d"] += 1; r["pts"] += 1
            else:
                r["l"] += 1
    return rows


def _head_to_head(tied_names, matches):
    """Mini-table (pts, gd, gf) among the tied teams, played games only."""
    h = {n: {"pts": 0, "gd": 0, "gf": 0} for n in tied_names}
    s = set(tied_names)
    for m in matches:
        if not is_played(m):
            continue
        t1, t2 = m["team1"], m["team2"]
        if t1 not in s or t2 not in s:
            continue
        g1, g2 = m["score"]["ft"]
        for t, gf, ga in ((t1, g1, g2), (t2, g2, g1)):
            h[t]["gf"] += gf
            h[t]["gd"] += gf - ga
            if gf > ga:
                h[t]["pts"] += 3
            elif gf == ga:
                h[t]["pts"] += 1
    return h


def sort_group(rows, matches):
    """Sort rows applying FIFA tiebreakers; returns ordered list of rows."""
    names = list(rows)
    # 1-3: overall points, gd, gf
    names.sort(key=lambda n: (rows[n]["pts"], rows[n]["gd"], rows[n]["gf"], ),
               reverse=True)

    # 4: head-to-head within blocks still tied on (pts, gd, gf)
    def block_key(n):
        return (rows[n]["pts"], rows[n]["gd"], rows[n]["gf"])

    ordered = []
    i = 0
    while i < len(names):
        j = i
        while j + 1 < len(names) and block_key(names[j + 1]) == block_key(names[i]):
            j += 1
        block = names[i:j + 1]
        if len(block) > 1:
            h = _head_to_head(block, matches)
            block.sort(
                key=lambda n: (h[n]["pts"], h[n]["gd"], h[n]["gf"], ),
                reverse=True,
            )
            # 5/6 fair play & lots unavailable -> stable alphabetical fallback
            # (re-sort sub-blocks that are still fully tied on h2h)
            block = _alpha_tiebreak(block, h, rows, matches)
        ordered.extend(block)
        i = j + 1
    return [rows[n] for n in ordered]


def _alpha_tiebreak(block, h, rows, matches):
    out = []
    i = 0
    keyf = lambda n: (h[n]["pts"], h[n]["gd"], h[n]["gf"])
    while i < len(block):
        j = i
        while j + 1 < len(block) and keyf(block[j + 1]) == keyf(block[i]):
            j += 1
        sub = sorted(block[i:j + 1])  # alphabetical, last resort
        out.extend(sub)
        i = j + 1
    return out


# --------------------------------------------------------------------------- #
# qualification logic (brute force over remaining group results)
# --------------------------------------------------------------------------- #
def _scenarios_points(rows, matches, team_names):
    """Yield dict name->final points for every W/D/L combo of remaining games."""
    base = {n: rows[n]["pts"] for n in team_names}
    remaining = [m for m in matches if not is_played(m)
                 and m["team1"] in base and m["team2"] in base]
    for combo in product((0, 1, 2), repeat=len(remaining)):
        pts = dict(base)
        for outcome, m in zip(combo, remaining):
            if outcome == 0:          # team1 win
                pts[m["team1"]] += 3
            elif outcome == 1:        # draw
                pts[m["team1"]] += 1
                pts[m["team2"]] += 1
            else:                     # team2 win
                pts[m["team2"]] += 3
        yield pts


def analyze_group(team_names, rows, matches):
    """
    Returns per-team dict:
      {name: {"qualified_top2","group_winner","cannot_top2",
              "max_pts","third_floor_contrib"}}
    Also returns group-level third_floor (min possible points of the team that
    finishes 3rd, over all scenarios) used for the best-third elimination test.
    """
    info = {n: {"qualified_top2": True, "group_winner": True,
                "cannot_top2": True, "max_pts": 0} for n in team_names}
    third_floor = None
    any_scenario = False

    for pts in _scenarios_points(rows, matches, team_names):
        any_scenario = True
        for n in team_names:
            info[n]["max_pts"] = max(info[n]["max_pts"], pts[n])
        # worst-case rank for each team (lose every point tie)
        for n in team_names:
            better = sum(1 for o in team_names if o != n and pts[o] > pts[n])
            equal = sum(1 for o in team_names if o != n and pts[o] == pts[n])
            rank_worst = better + equal + 1   # all ties go against n
            rank_best = better + 1            # all ties favour n
            if rank_worst > 2:
                info[n]["qualified_top2"] = False
            if rank_worst > 1:
                info[n]["group_winner"] = False
            if rank_best <= 2:
                info[n]["cannot_top2"] = False
        # points of the 3rd-placed team this scenario (3rd largest value)
        sorted_pts = sorted(pts.values(), reverse=True)
        third_pts = sorted_pts[2] if len(sorted_pts) >= 3 else 0
        third_floor = third_pts if third_floor is None else min(third_floor, third_pts)

    if not any_scenario:  # no teams? defensive
        third_floor = 0
    return info, third_floor


def apply_best_third_elimination(groups_info, third_floors):
    """
    Mark teams eliminated. A team is eliminated iff it cannot reach top-2 AND
    its max possible points are below the guaranteed floor of the 8th-best
    third among the *other* groups (a sound lower bound on the 8th third).
    """
    for letter, info in groups_info.items():
        others = [third_floors[g] for g in third_floors if g != letter]
        others.sort(reverse=True)
        # 8th largest guaranteed third floor among the other 11 groups
        guaranteed_8th = others[7] if len(others) >= 8 else (others[-1] if others else 0)
        for n, d in info.items():
            d["eliminated"] = bool(d["cannot_top2"] and d["max_pts"] < guaranteed_8th)


# --------------------------------------------------------------------------- #
# top-level assembly
# --------------------------------------------------------------------------- #
def build_standings(teams, matches):
    """Returns the list of 12 group dicts ready for templating."""
    teams_by_name = {t["name"]: t for t in teams}
    groups_in = {}
    for t in teams:
        groups_in.setdefault(t["group"], []).append(t["name"])

    groups_info = {}
    third_floors = {}
    rows_by_group = {}
    for letter in GROUP_LETTERS:
        names = groups_in.get(letter, [])
        gms = group_matches(matches, letter)
        rows = compute_rows(names, teams_by_name, gms)
        info, tf = analyze_group(names, rows, gms)
        rows_by_group[letter] = (rows, gms)
        groups_info[letter] = info
        third_floors[letter] = tf

    apply_best_third_elimination(groups_info, third_floors)

    out_groups = []
    for letter in GROUP_LETTERS:
        rows, gms = rows_by_group[letter]
        ordered = sort_group(rows, gms)
        info = groups_info[letter]
        teams_out = []
        for pos, r in enumerate(ordered, 1):
            d = info[r["name"]]
            teams_out.append({
                "pos": pos,
                "name": r["name"],
                "code": r["code"],
                "flag": r["flag"],
                "p": r["p"], "w": r["w"], "d": r["d"], "l": r["l"],
                "gf": r["gf"], "ga": r["ga"],
                "gd": r["gd"],
                # signed string for display, e.g. "+3" / "0" / "-2"
                "gd_str": ("+%d" % r["gd"]) if r["gd"] > 0 else str(r["gd"]),
                "pts": r["pts"],
                "qualified": bool(d["qualified_top2"]),
                "winner": bool(d["group_winner"]),
                "eliminated": bool(d.get("eliminated", False)),
            })
        out_groups.append({"name": letter, "teams": teams_out})
    return out_groups
