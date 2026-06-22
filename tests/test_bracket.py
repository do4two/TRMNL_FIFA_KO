#!/usr/bin/env python3
"""Unit checks for the knockout-bracket model (src/bracket.py).

Run: .venv/bin/python tests/test_bracket.py
Covers: match outcome (ft/et/pen), slot resolution (names, W*/L*, group
positions, thirds), tree topology/ordering, and full-bracket assembly for the
pre-tournament placeholder state and a played-out state.
"""
import json
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import bracket as B  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def m(num, rnd, t1, t2, score=None):
    d = {"num": num, "round": rnd, "team1": t1, "team2": t2}
    if score is not None:
        d["score"] = score
    return d


# --------------------------------------------------------------------------- #
# outcome()
# --------------------------------------------------------------------------- #
check("outcome: not played -> None", B.outcome(m(89, "Round of 16", "W74", "W77")) is None)
check("outcome: ft decisive team1", B.outcome(m(1, "Final", "A", "B", {"ft": [2, 1]}))["win"] == 0)
check("outcome: ft decisive team2", B.outcome(m(1, "Final", "A", "B", {"ft": [0, 3]}))["win"] == 1)
check("outcome: extra time", B.outcome(m(1, "Final", "A", "B", {"ft": [1, 1], "et": [2, 1]})) == {"win": 0, "note": "n.V."})
check("outcome: penalties", B.outcome(m(1, "Final", "A", "B", {"ft": [1, 1], "pen": [3, 4]})) == {"win": 1, "note": "i.E."})
check("outcome: tie no et/pen -> None", B.outcome(m(1, "Final", "A", "B", {"ft": [1, 1]})) is None)

# --------------------------------------------------------------------------- #
# slot resolution
# --------------------------------------------------------------------------- #
teams = [
    {"name": "Brazil", "fifa_code": "BRA", "flag_icon": "BR", "group": "A"},
    {"name": "Mexico", "fifa_code": "MEX", "flag_icon": "MX", "group": "A"},
]
tbn = {t["name"]: t for t in teams}

ko = {73: m(73, "Round of 32", "Brazil", "Mexico", {"ft": [2, 0]}),
      89: m(89, "Round of 16", "W73", "L73")}

r_real = B.resolve_slot("Brazil", ko, tbn, {})
check("slot: real name resolves", r_real["resolved"] and r_real["code"] == "BRA")

r_w = B.resolve_slot("W73", ko, tbn, {})
check("slot: W73 -> winner Brazil", r_w["resolved"] and r_w["code"] == "BRA")
r_l = B.resolve_slot("L73", ko, tbn, {})
check("slot: L73 -> loser Mexico", r_l["resolved"] and r_l["code"] == "MEX")

ko_open = {89: m(89, "Round of 16", "W74", "W77")}
r_open = B.resolve_slot("W74", ko_open, tbn, {})
check("slot: undecided W74 -> placeholder S.74", (not r_open["resolved"]) and r_open["code"] == "S.74")
r_lopen = B.resolve_slot("L101", {}, tbn, {})
check("slot: missing L101 -> placeholder V.101", (not r_lopen["resolved"]) and r_lopen["code"] == "V.101")

gp = {"A": {1: {"name": "Brazil", "code": "BRA", "flag": "BR"},
            2: {"name": "Mexico", "code": "MEX", "flag": "MX"}}}
check("slot: 1A resolves to group winner", B.resolve_slot("1A", {}, tbn, gp)["code"] == "BRA")
check("slot: 2A resolves to runner-up", B.resolve_slot("2A", {}, tbn, gp)["code"] == "MEX")
check("slot: 1B unknown -> placeholder", B.resolve_slot("1B", {}, tbn, {})["code"] == "1B")
check("slot: third slot -> '3.' placeholder", B.resolve_slot("3A/B/C/D/F", {}, tbn, {})["code"] == "3.")

# --------------------------------------------------------------------------- #
# topology / ordering against the real fixture list
# --------------------------------------------------------------------------- #
doc = json.load(open(os.path.join(ROOT, "data", "worldcup.json"), encoding="utf-8"))
matches = doc["matches"]
real_ko = B.knockout_matches(matches)
check("topology: 32 KO matches found", len(real_ko) == 32)

left = B.collect_half(B._source_num(real_ko[104]["team1"]), real_ko)
right = B.collect_half(B._source_num(real_ko[104]["team2"]), real_ko)
check("topology: left R32 order", left["r32"] == [74, 77, 73, 75, 83, 84, 81, 82])
check("topology: right R32 order", right["r32"] == [76, 78, 79, 80, 86, 88, 85, 87])
check("topology: left has 8/4/2/1", [len(left[k]) for k in ("r32", "r16", "qf", "sf")] == [8, 4, 2, 1])
check("topology: halves are disjoint",
      set(left["r32"]).isdisjoint(right["r32"]))

# --------------------------------------------------------------------------- #
# full assembly: pre-tournament (real cached data, no KO played)
# --------------------------------------------------------------------------- #
real_teams = json.load(open(os.path.join(ROOT, "data", "worldcup.teams.json"), encoding="utf-8"))
pre = B.build_bracket(real_teams, matches)
check("pre: 0 KO decided", pre["ko_played"] == 0)
check("pre: no champion", pre["champion"] is None)
check("pre: final is placeholder", not pre["final"]["t1"]["resolved"])
check("pre: 8 R32 matches per side", len(pre["left"]["r32"]) == 8 and len(pre["right"]["r32"]) == 8)
check("pre: robust to no results (final not decided)", pre["final"]["decided"] is False)
# Mexico has six points and beat South Korea head-to-head. Even before the
# final group games, no remaining scenario can dislodge Mexico from first.
pre79 = next(x for x in pre["right"]["r32"] if x["num"] == 79)
check("clinch: incomplete Group A already resolves 1A = Mexico",
      pre79["t1"]["code"] == "MEX" and pre79["t1"]["resolved"])

# --------------------------------------------------------------------------- #
# full assembly: a played-out branch resolves and crowns a champion
# --------------------------------------------------------------------------- #
def overlay(matches, ov):
    by = {x["num"]: x for x in matches if isinstance(x.get("num"), int)}
    import copy
    matches = copy.deepcopy(matches)
    by = {x["num"]: x for x in matches if isinstance(x.get("num"), int)}
    for k, v in ov.items():
        x = by[k]
        if "team1" in v:
            x["team1"] = v["team1"]
        if "team2" in v:
            x["team2"] = v["team2"]
        if "score" in v:
            x["score"] = v["score"]
    return matches


A, Bn = real_teams[0]["name"], real_teams[1]["name"]
ovm = overlay(matches, {
    101: {"team1": A, "team2": Bn, "score": {"ft": [1, 0]}},
    102: {"team1": A, "team2": Bn, "score": {"ft": [0, 2]}},
    104: {"score": {"ft": [1, 1], "pen": [4, 2]}},
})
done = B.build_bracket(real_teams, ovm)
check("played: final t1 = winner of 101 (A)", done["final"]["t1"]["name"] == A)
check("played: final t2 = winner of 102 (B)", done["final"]["t2"]["name"] == Bn)
check("played: champion via penalties = A", done["champion"]["name"] == A)
check("played: final note i.E.", done["final"]["note"] == "i.E.")

# --------------------------------------------------------------------------- #
# integration: completing a group fills its 1X/2X knockout slots
# --------------------------------------------------------------------------- #
import copy  # noqa: E402
gmatches = copy.deepcopy(matches)
for x in gmatches:
    if x.get("group") == "Group A" and not x.get("score"):
        if x["team1"] == "Czech Republic":      # Czech vs Mexico -> Mexico 0:1
            x["score"] = {"ft": [0, 1]}
        else:                                    # South Africa vs South Korea -> 0:2
            x["score"] = {"ft": [0, 2]}
gp = B._group_positions(real_teams, gmatches)
check("group A complete -> 1A = Mexico", gp.get("A", {}).get(1, {}).get("code") == "MEX")
check("group A complete -> 2A = South Korea", gp.get("A", {}).get(2, {}).get("code") == "KOR")
gbr = B.build_bracket(real_teams, gmatches)
# R32 match 79 = "1A" vs a third-place slot; it lives on the right half
m79 = next(x for x in gbr["right"]["r32"] if x["num"] == 79)
check("match 79 t1 auto-fills to MEX once group A done", m79["t1"]["code"] == "MEX" and m79["t1"]["resolved"])

# --------------------------------------------------------------------------- #
# integration: a head-to-head clinch resolves before all group games are played
# --------------------------------------------------------------------------- #
ematches = copy.deepcopy(matches)
for x in ematches:
    if x.get("group") != "Group E":
        continue
    pair = {x["team1"], x["team2"]}
    if pair == {"Germany", "Ivory Coast"}:
        x["score"] = {"ft": [2, 1]}
    elif pair == {"Ecuador", "Curaçao"}:
        x["score"] = {"ft": [0, 0]}

egp = B._group_positions(real_teams, ematches)
check("clinch: incomplete Group E resolves 1E = Germany",
      egp.get("E", {}).get(1, {}).get("code") == "GER")
check("clinch: incomplete Group E does not invent a runner-up",
      2 not in egp.get("E", {}))

# Group D is not yet a guaranteed winner in the cached state: a three-team
# points tie can still require score-margin tiebreakers.
dgp = B._group_positions(real_teams, matches)
check("clinch: unresolved Group D keeps 1D open",
      1 not in dgp.get("D", {}))

# --------------------------------------------------------------------------- #
print()
if _fails:
    print("%d FAILED: %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("all bracket checks passed")
