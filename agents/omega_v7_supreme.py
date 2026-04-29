"""
OMEGA v7 SUPREME — Orbit Wars: Competition-Grade Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Built strictly to competition spec (April 2026):
  - Turn order: comet_expiry→spawn→fleet_launch→production→movement→rotation→combat
  - Fleet speed: 1.0 + 5.0*(log(ships)/log(1000))^1.5
  - 2P diagonal start (Q1 vs Q4), 4P four-corner start
  - Comets spawn at steps 50,150,250,350,450 in groups of 4
  - Final score = ships_on_planets + ships_in_fleets
  - actTimeout = 1.0s per turn
"""

import math
import time
from collections import defaultdict, namedtuple
from dataclasses import dataclass, field
from enum import Enum

# ════════════════════════════════════════════════════════
# § 1  GAME CONSTANTS  (exact competition spec)
# ════════════════════════════════════════════════════════

BOARD = 100.0; CENTER_X = 50.0; CENTER_Y = 50.0
SUN_R = 10.0; MAX_SPEED = 6.0; SUN_SAFETY = 1.65
ROTATION_LIMIT = 50.0; TOTAL_STEPS = 500
HORIZON = 115; LAUNCH_CLR = 0.12; INTERCEPT_TOL = 1

# Comet spawn turns
COMET_SPAWN_TURNS = {50, 150, 250, 350, 450}

# Phase thresholds
EARLY_LIMIT = 45; OPENING_LIMIT = 90
LATE_REMAINING = 80; VERY_LATE_REMAINING = 40
TOTAL_WAR_REMAINING = 65; ENDGAME_REMAINING = 110
HOARD_REMAINING = 40   # stop new attacks, hoard ships

# Opening book
OPENING_BOOK_TURNS = 60
OPENING_STATIC_BOOST = 2.20
OPENING_DIAG_BOOST   = 1.55   # diagonal-symmetry neutrals

# ════════════════════════════════════════════════════════
# § 2  VALUE MULTIPLIERS
# ════════════════════════════════════════════════════════

INDIRECT_SCALE = 0.15
IND_FRIENDLY_W = 0.35; IND_NEUTRAL_W = 0.9; IND_ENEMY_W = 1.25
PROD_EXP = 1.28          # prod^1.28 captures snowball better than ^1.25

STATIC_NEUTRAL_VM   = 1.50
STATIC_HOSTILE_VM   = 1.95
ROT_OPEN_VM         = 0.85
HOSTILE_VM          = 2.35
OPEN_HOSTILE_VM     = 1.65
SAFE_NEUTRAL_VM     = 1.35
CONTESTED_NEUTRAL_VM= 0.62
EARLY_NEUTRAL_VM    = 1.40
COMET_VM            = 0.62
SNIPE_VM            = 1.25
SWARM_VM            = 1.12
REINFORCE_VM        = 1.42
CRASH_VM            = 1.32
GANG_UP_VM          = 1.62
EXPOSED_VM          = 2.55   # enemy sent ≥42% ships away
RACE_WIN_VM         = 1.60
FINISH_HOSTILE_VM   = 1.55
BEHIND_ROT_VM       = 0.85
PROD_DENY_VM        = 1.45
FRONTIER_BONUS_VM   = 1.22   # battle-front planets
KILL_SHOT_VM        = 2.65   # overwhelming finish force
CLUSTER_BONUS_VM    = 1.10   # near my other planets

# Economic mode
ECO_EXPAND_THRESH     = 1.35; ECO_AGGRO_THRESH = 0.72
ECO_EXPAND_NEUTRAL_VM = 1.35; ECO_EXPAND_HOSTILE_VM = 0.75
ECO_AGGRO_HOSTILE_VM  = 1.55; ECO_AGGRO_NEUTRAL_VM = 0.75
PROD_DENY_THRESHOLD   = 4

# Positional
GATEWAY_VM = 1.24; GATEWAY_DIST_THRESH = 26.0
FRONTIER_DIST_MAX = 30.0
CLUSTER_DIST_MAX  = 22.0     # my planets within this range are a cluster

# Weakest enemy
WEAKEST_VM_FFA = 1.72; WEAKEST_VM_1V1 = 1.42
ELIM_BONUS = 90.0; WEAK_THRESH = 155

# Multi-front pressure
PRESSURE_FRONT_MIN = 3; PRESSURE_BONUS_PER = 0.13; PRESSURE_MAX_MULT = 1.50

# ════════════════════════════════════════════════════════
# § 3  MARGINS, COSTS, TIMING
# ════════════════════════════════════════════════════════

NEUTRAL_MARGIN_BASE = 2; NEUTRAL_MARGIN_PROD_W = 2; NEUTRAL_MARGIN_CAP = 8
HOSTILE_MARGIN_BASE = 3; HOSTILE_MARGIN_PROD_W = 2; HOSTILE_MARGIN_CAP = 12
STATIC_MARGIN = 4; CONTESTED_MARGIN = 5; FFA_MARGIN = 2
LONG_TRAVEL_START = 18; LONG_TRAVEL_DIV = 3; LONG_TRAVEL_CAP = 8
COMET_MARGIN_RELIEF = 6; FINISH_SEND_BONUS = 4

ATTACK_TURN_W = 0.48; SNIPE_TURN_W = 0.40; DEF_TURN_W = 0.38
REINF_TURN_W = 0.33; RECAP_TURN_W = 0.50

TSUNAMI_RATIO = 0.87; TSUNAMI_THRESH = 1.8; TSUNAMI_MIN_SHIPS = 35
TSUNAMI_TURNS_SAVED_MIN = 2; TSUNAMI_MAX_EXTRA_FRAC = 0.45

SAFE_NEUTRAL_MARGIN = 2; CONTESTED_NEUTRAL_MARGIN = 2
RACE_MIN_ADVANTAGE = 2; RACE_MARGIN_TURNS = 1

PROACT_HORIZON = 14; PROACT_RATIO = 0.33
MULTI_PROACT_HOR = 18; MULTI_PROACT_RATIO = 0.44; MULTI_STACK_WIN = 5
REACT_MY_TOP_K = 4; REACT_EN_TOP_K = 4; PROACT_EN_TOP_K = 3

REINF_ENABLED = True; REINF_MIN_PROD = 2; REINF_MAX_TRAVEL = 22
REINF_SAFETY = 2; REINF_MAX_SRC_FRAC = 0.75
REINF_MIN_FUTURE = 40; REINF_LOOKAHEAD = 20

DEF_LOOKAHEAD = 30; DEF_SHIP_VALUE = 0.66; DEF_FRONTIER_M = 1.20
DEF_SEND_MARGIN = 1; DEF_SEND_PROD_W = 1

RECAP_LOOKAHEAD = 12; RECAP_VM_MULT = 0.92
RECAP_FRONTIER_M = 1.14; RECAP_PROD_W = 0.6; RECAP_IMMED_W = 0.4

FOLLOWUP_MIN = 8; LOW_COMET_PROD = 1; LATE_BUFFER = 5; VERY_LATE_BUFFER = 3
PARTIAL_MIN = 6; MULTI_TOP_K = 5; MULTI_ETA_TOL = 2; MULTI_PLAN_PEN = 0.97
HOSTILE_SWARM_TOL = 1
THREE_SRC_ENABLED = True; THREE_SRC_MIN_SHIPS = 16
THREE_SRC_TOL = 1; THREE_SRC_PEN = 0.93

CRASH_ENABLED = True; CRASH_MIN_SHIPS = 6; CRASH_ETA_WIN = 3; CRASH_DELAY = 1
GANG_POST_DELAY = 2; GANG_ETA_WIN = 4; GANG_WEAK_THRESH = 26

RUSH_DETECT_STEP_MAX = 65; RUSH_FLEET_MIN = 26; RUSH_HOME_ETA_MAX = 26

INTERCEPT_ETA_MAX = 22; INTERCEPT_ENABLED = True

VULN_SENT_RATIO = 0.40; VULN_MIN_SENT = 6

WIN_SECURE_RATIO = 1.35; WIN_DESPERATE_RATIO = 0.72
WIN_SECURE_MARGIN_M = 0.82; WIN_DESPERATE_RISK_M = 1.32

STATIC_SCORE_M = 1.22; EARLY_STATIC_SCORE_M = 1.38
FFA_ROT_SCORE_M = 0.80; DENSE_STATIC_THRESH = 4; DENSE_ROT_SCORE_M = 0.82
SNIPE_SCORE_M = 1.20; SWARM_SCORE_M = 1.08; CRASH_SCORE_M = 1.14
EXPOSED_SCORE_M = 1.45; WEAKEST_SCORE_M = 1.35; RACE_SCORE_MULT = 1.26

ONE_V_ONE_DOM_THRESH = 0.20; ONE_V_ONE_AGG_RESERVE = 0.30

LATE_SHIP_W = 0.95; VERY_LATE_SHIP_W = 1.65; HOARD_SHIP_W = 2.20

DOOMED_EVAC_LIMIT = 24; DOOMED_MIN_SHIPS = 8

REAR_MIN_SHIPS = 14; REAR_DIST_RATIO = 1.25; REAR_STAGE_PROG = 0.78
REAR_RATIO_2P = 0.65; REAR_RATIO_FFA = 0.58; REAR_SEND_MIN = 10; REAR_MAX_TRAVEL = 40

BEHIND_DOM = -0.18; AHEAD_DOM = 0.13; FINISH_DOM = 0.26; FINISH_PROD_R = 1.12
AHEAD_MRG_B = 0.14; BEHIND_MRG_P = 0.06; FINISH_MRG_B = 0.14

SOFT_DEADLINE = 0.85; HEAVY_MIN_TIME = 0.14; OPT_MIN_TIME = 0.07
HEAVY_PLANET_LIM = 40

SAFE_OPEN_PROD_TH = 4; SAFE_OPEN_TURN_LIM = 10
ROT_OPEN_MAX_TURNS = 13; ROT_OPEN_LOW_PROD = 2
FFA_ROT_REACT_GAP = 3; FFA_ROT_SEND_RATIO = 0.52
FFA_ROT_TURN_LIM = 10; COMET_MAX_CHASE = 10

# ════════════════════════════════════════════════════════
# § 4  DATA TYPES
# ════════════════════════════════════════════════════════

Planet = namedtuple("Planet", ["id","owner","x","y","radius","ships","production"])
Fleet  = namedtuple("Fleet",  ["id","owner","x","y","angle","from_planet_id","ships"])

class EcoMode(Enum):
    EXPAND = "expand"; BALANCED = "balanced"; AGGRO = "aggro"

@dataclass(frozen=True)
class ShotOption:
    score:       float
    src_id:      int
    target_id:   int
    angle:       float
    turns:       int
    needed:      int
    send_cap:    int
    mission:     str      = "capture"
    anchor_turn: int|None = None

@dataclass
class Mission:
    kind: str; score: float; target_id: int; turns: int
    options: list = field(default_factory=list)

# ════════════════════════════════════════════════════════
# § 5  PHYSICS ENGINE
# ════════════════════════════════════════════════════════

def dist(ax, ay, bx, by):  return math.hypot(ax-bx, ay-by)
def orbital_radius(p):     return dist(p.x, p.y, CENTER_X, CENTER_Y)
def is_static_planet(p):   return orbital_radius(p) + p.radius >= ROTATION_LIMIT

def fleet_speed(ships: int) -> float:
    if ships <= 1: return 1.0
    r = max(0.0, min(1.0, math.log(ships) / math.log(1000.0)))
    return 1.0 + (MAX_SPEED - 1.0) * (r ** 1.5)

def speed_optimal_send(needed, available, distance, prod_per_turn):
    if available <= 0 or needed <= 0: return needed
    if available < needed:            return needed
    base_speed = fleet_speed(max(1, needed))
    base_turns = max(1, int(math.ceil(distance / base_speed)))
    if available >= needed * TSUNAMI_THRESH and available >= TSUNAMI_MIN_SHIPS:
        cand       = min(available, max(needed, int(available * TSUNAMI_RATIO)))
        cand_turns = max(1, int(math.ceil(distance / fleet_speed(max(1, cand)))))
        ts         = base_turns - cand_turns
        xs         = cand - needed
        if ts >= TSUNAMI_TURNS_SAVED_MIN:          return cand
        if xs <= available * TSUNAMI_MAX_EXTRA_FRAC: return cand
    modest = min(available, int(needed * 1.20))
    if modest > needed:
        if base_turns - max(1,int(math.ceil(distance/fleet_speed(max(1,modest))))) >= 1:
            return modest
    return min(available, max(needed, int(needed * 1.05)))

def pt_seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2-x1, y2-y1; sq = dx*dx+dy*dy
    if sq <= 1e-9: return dist(px, py, x1, y1)
    t = max(0.0, min(1.0, ((px-x1)*dx+(py-y1)*dy)/sq))
    return dist(px, py, x1+t*dx, y1+t*dy)

def seg_hits_sun(x1, y1, x2, y2):
    return pt_seg_dist(CENTER_X, CENTER_Y, x1, y1, x2, y2) < SUN_R + SUN_SAFETY

def launch_pt(sx, sy, sr, angle):
    c = sr + LAUNCH_CLR
    return sx + math.cos(angle)*c, sy + math.sin(angle)*c

def safe_angle_dist(sx, sy, sr, tx, ty, tr, bypass_tries=6):
    """Try direct angle first; if sun blocked, try bypass angles."""
    base_angle = math.atan2(ty-sy, tx-sx)
    for i in range(bypass_tries + 1):
        if i == 0:
            angle = base_angle
        elif i <= bypass_tries // 2:
            angle = base_angle + i * 0.15
        else:
            angle = base_angle - (i - bypass_tries // 2) * 0.15
        lx, ly = launch_pt(sx, sy, sr, angle)
        d = max(0.0, dist(sx, sy, tx, ty) - (sr + LAUNCH_CLR) - tr)
        ex = lx + math.cos(angle)*d; ey = ly + math.sin(angle)*d
        if not seg_hits_sun(lx, ly, ex, ey):
            return angle, d
    return None

def predict_planet_pos(planet, init_by_id, ang_vel, turns):
    init = init_by_id.get(planet.id)
    if init is None: return planet.x, planet.y
    r = dist(init.x, init.y, CENTER_X, CENTER_Y)
    if r + init.radius >= ROTATION_LIMIT: return planet.x, planet.y
    cur = math.atan2(planet.y - CENTER_Y, planet.x - CENTER_X)
    new = cur + ang_vel * turns
    return CENTER_X + r*math.cos(new), CENTER_Y + r*math.sin(new)

def predict_comet_pos(pid, comets, turns):
    for g in comets:
        pids = g.get("planet_ids", [])
        if pid not in pids: continue
        idx = pids.index(pid); paths = g.get("paths", []); pi = g.get("path_index", 0)
        if idx >= len(paths): return None
        fi = pi + int(turns)
        if 0 <= fi < len(paths[idx]): return paths[idx][fi][0], paths[idx][fi][1]
        return None
    return None

def comet_life(pid, comets):
    for g in comets:
        pids = g.get("planet_ids", [])
        if pid not in pids: continue
        idx = pids.index(pid); paths = g.get("paths", []); pi = g.get("path_index", 0)
        if idx < len(paths): return max(0, len(paths[idx]) - pi)
    return 0

def estimate_arrival(sx, sy, sr, tx, ty, tr, ships):
    safe = safe_angle_dist(sx, sy, sr, tx, ty, tr)
    if safe is None: return None
    angle, d = safe
    return angle, max(1, int(math.ceil(d / fleet_speed(max(1, ships)))))

def travel_time(sx, sy, sr, tx, ty, tr, ships):
    e = estimate_arrival(sx, sy, sr, tx, ty, tr, ships)
    return e[1] if e else 10**9

def predict_target_pos(target, turns, init_by_id, ang_vel, comets, comet_ids):
    if target.id in comet_ids: return predict_comet_pos(target.id, comets, turns)
    return predict_planet_pos(target, init_by_id, ang_vel, turns)

def target_can_move(target, init_by_id, comet_ids):
    if target.id in comet_ids: return True
    init = init_by_id.get(target.id)
    if init is None: return False
    return dist(init.x, init.y, CENTER_X, CENTER_Y) + init.radius < ROTATION_LIMIT

def search_intercept(src, target, ships, init_by_id, ang_vel, comets, comet_ids):
    best, best_sc = None, None
    max_t = min(HORIZON, 60)
    if target.id in comet_ids:
        max_t = min(max_t, max(0, comet_life(target.id, comets)-1))
    for ct in range(1, max_t+1):
        pos = predict_target_pos(target, ct, init_by_id, ang_vel, comets, comet_ids)
        if pos is None: continue
        e = estimate_arrival(src.x, src.y, src.radius, pos[0], pos[1], target.radius, ships)
        if e is None: continue
        if abs(e[1]-ct) > INTERCEPT_TOL: continue
        at = max(e[1], ct)
        ap = predict_target_pos(target, at, init_by_id, ang_vel, comets, comet_ids)
        if ap is None: continue
        c = estimate_arrival(src.x, src.y, src.radius, ap[0], ap[1], target.radius, ships)
        if c is None: continue
        delta = abs(c[1]-at)
        if delta > INTERCEPT_TOL: continue
        sc = (delta, c[1], ct)
        if best is None or sc < best_sc: best_sc, best = sc, (c[0], c[1], ap[0], ap[1])
    return best

def aim_with_prediction(src, target, ships, init_by_id, ang_vel, comets, comet_ids):
    e = estimate_arrival(src.x, src.y, src.radius, target.x, target.y, target.radius, ships)
    if e is None:
        if not target_can_move(target, init_by_id, comet_ids): return None
        return search_intercept(src, target, ships, init_by_id, ang_vel, comets, comet_ids)
    tx, ty = target.x, target.y
    for _ in range(6):
        _, turns = e
        pos = predict_target_pos(target, turns, init_by_id, ang_vel, comets, comet_ids)
        if pos is None: return None
        ntx, nty = pos
        ne = estimate_arrival(src.x, src.y, src.radius, ntx, nty, target.radius, ships)
        if ne is None:
            if not target_can_move(target, init_by_id, comet_ids): return None
            return search_intercept(src, target, ships, init_by_id, ang_vel, comets, comet_ids)
        if abs(ntx-tx)<0.25 and abs(nty-ty)<0.25 and abs(ne[1]-turns)<=INTERCEPT_TOL:
            return ne[0], ne[1], ntx, nty
        tx, ty = ntx, nty; e = ne
    fe = estimate_arrival(src.x, src.y, src.radius, tx, ty, target.radius, ships)
    if fe is None:
        return search_intercept(src, target, ships, init_by_id, ang_vel, comets, comet_ids)
    return fe[0], fe[1], tx, ty

# ════════════════════════════════════════════════════════
# § 6  SIMULATION ENGINE
# ════════════════════════════════════════════════════════

def fleet_target_planet(fleet, planets):
    best_p, best_t = None, 1e9
    dx, dy = math.cos(fleet.angle), math.sin(fleet.angle)
    sp     = fleet_speed(fleet.ships)
    for p in planets:
        px, py  = p.x-fleet.x, p.y-fleet.y
        proj    = px*dx + py*dy
        if proj < 0: continue
        perp_sq = px*px + py*py - proj*proj
        if perp_sq >= p.radius*p.radius: continue
        hit = max(0.0, proj - math.sqrt(max(0.0, p.radius*p.radius-perp_sq)))
        t   = hit / sp
        if t <= HORIZON and t < best_t: best_t, best_p = t, p
    if best_p is None: return None, None
    return best_p, int(math.ceil(best_t))

def build_arrival_ledger(fleets, planets):
    abp = {p.id: [] for p in planets}
    for f in fleets:
        tp, eta = fleet_target_planet(f, planets)
        if tp is None: continue
        abp[tp.id].append((eta, f.owner, int(f.ships)))
    return abp

def resolve_arrivals(owner, garrison, arrivals):
    by_owner = {}
    for _, ao, s in arrivals: by_owner[ao] = by_owner.get(ao, 0) + s
    if not by_owner: return owner, max(0.0, garrison)
    srt = sorted(by_owner.items(), key=lambda x: x[1], reverse=True)
    top_o, top_s = srt[0]
    if len(srt) > 1:
        sec = srt[1][1]
        if top_s == sec: surv_o, surv_s = -1, 0
        else:            surv_o, surv_s = top_o, top_s - sec
    else: surv_o, surv_s = top_o, top_s
    if surv_s <= 0: return owner, max(0.0, garrison)
    if owner == surv_o: return owner, garrison + surv_s
    garrison -= surv_s
    if garrison < 0: return surv_o, -garrison
    return owner, garrison

def normalize_arrivals(arrivals, horizon):
    events = []
    for t, o, s in arrivals:
        if s <= 0: continue
        eta = max(1, int(math.ceil(t)))
        if eta > horizon: continue
        events.append((eta, o, int(s)))
    events.sort(); return events

def simulate_timeline(planet, arrivals, player, horizon):
    horizon   = max(0, int(math.ceil(horizon)))
    events    = normalize_arrivals(arrivals, horizon)
    by_turn   = defaultdict(list)
    for item in events: by_turn[item[0]].append(item)
    owner     = planet.owner
    garrison  = float(planet.ships)
    owner_at  = {0: owner}
    ships_at  = {0: max(0.0, garrison)}
    fall_turn = None
    for turn in range(1, horizon+1):
        if owner != -1: garrison += planet.production  # production first
        group = by_turn.get(turn, [])
        prev  = owner
        if group:
            owner, garrison = resolve_arrivals(owner, garrison, group)
            if prev == player and owner != player and fall_turn is None:
                fall_turn = turn
        owner_at[turn] = owner
        ships_at[turn] = max(0.0, garrison)
    
    keep_needed = 0; holds_full = True
    if planet.owner == player:
        def survives(keep):
            so, sg = planet.owner, float(keep)
            for t in range(1, horizon+1):
                if so != -1: sg += planet.production
                gr = by_turn.get(t, [])
                if gr:
                    so, sg = resolve_arrivals(so, sg, gr)
                    if so != player: return False
            return so == player
        if survives(int(planet.ships)):
            lo, hi = 0, int(planet.ships)
            while lo < hi:
                mid = (lo+hi)//2
                if survives(mid): hi = mid
                else:             lo = mid+1
            keep_needed = lo
        else:
            holds_full = False; keep_needed = int(planet.ships)
    return dict(owner_at=owner_at, ships_at=ships_at, keep_needed=keep_needed,
                fall_turn=fall_turn, holds_full=holds_full, horizon=horizon)

def state_at(tl, at):
    t = max(0, min(int(math.ceil(at)), tl["horizon"]))
    return (tl["owner_at"].get(t, tl["owner_at"][tl["horizon"]]),
            max(0.0, tl["ships_at"].get(t, tl["ships_at"][tl["horizon"]])))

def count_players(planets, fleets):
    owners = set()
    for p in planets:
        if p.owner != -1: owners.add(p.owner)
    for f in fleets: owners.add(f.owner)
    return max(2, len(owners))

def nearest_dist(px, py, planets):
    if not planets: return 10**9
    return min(dist(px, py, p.x, p.y) for p in planets)

def indirect_features(planet, planets, player):
    f = n = e = 0.0
    for o in planets:
        if o.id == planet.id: continue
        d = dist(planet.x, planet.y, o.x, o.y)
        if d < 1: continue
        fac = o.production / (d + 12.0)
        if   o.owner == player: f += fac
        elif o.owner == -1:     n += fac
        else:                   e += fac
    return f, n, e

def detect_vulnerable_planets(fleets, enemy_planets, player):
    vuln, sent_from = set(), defaultdict(int)
    for f in fleets:
        if f.owner == player or f.owner == -1: continue
        sent_from[f.from_planet_id] += int(f.ships)
    for p in enemy_planets:
        sent = sent_from.get(p.id, 0)
        if sent >= VULN_MIN_SENT and sent >= p.ships * VULN_SENT_RATIO:
            vuln.add(p.id)
    return vuln

def weakest_enemy_owner(enemy_planets, owner_strength, owner_prod):
    owners = set(p.owner for p in enemy_planets)
    if not owners: return None
    return min(owners, key=lambda o: owner_strength.get(o,0) + owner_prod.get(o,0)*15)

def highest_prod_enemy_planet(enemy_planets, owner_strength):
    if not enemy_planets: return None
    return max(enemy_planets, key=lambda p: p.production*10 + owner_strength.get(p.owner,0))

def compute_gateway_value(planet, enemy_planets):
    if not enemy_planets: return 1.0
    min_d = min(dist(planet.x, planet.y, e.x, e.y) for e in enemy_planets)
    if min_d <= GATEWAY_DIST_THRESH:
        ratio = max(0.0, 1.0 - min_d / GATEWAY_DIST_THRESH)
        return 1.0 + (GATEWAY_VM - 1.0) * ratio
    return 1.0

def compute_frontier_value(planet, enemy_planets):
    if not enemy_planets: return 1.0
    min_d = min(dist(planet.x, planet.y, e.x, e.y) for e in enemy_planets)
    if min_d <= FRONTIER_DIST_MAX:
        frac = max(0.0, 1.0 - min_d / FRONTIER_DIST_MAX)
        return 1.0 + (FRONTIER_BONUS_VM - 1.0) * frac
    return 1.0

def compute_cluster_bonus(planet, my_planets):
    """v7: my planets close together have fleet synergy."""
    count = sum(1 for p in my_planets if p.id != planet.id
                and dist(planet.x, planet.y, p.x, p.y) <= CLUSTER_DIST_MAX)
    if count == 0: return 1.0
    return min(CLUSTER_BONUS_VM, 1.0 + (CLUSTER_BONUS_VM-1.0) * min(count, 3) / 3)

def detect_rush(fleets, my_planets, player, step):
    if step > RUSH_DETECT_STEP_MAX: return False, 0, 999
    total_rush = 0; min_eta = 999
    for f in fleets:
        if f.owner == player or f.owner == -1: continue
        if int(f.ships) < RUSH_FLEET_MIN: continue
        dx, dy = math.cos(f.angle), math.sin(f.angle)
        for mp in my_planets:
            px, py = mp.x-f.x, mp.y-f.y; proj = px*dx+py*dy
            if proj <= 0: continue
            perp = abs(px*dy-py*dx)
            if perp > mp.radius+5: continue
            eta = int(math.ceil(proj/fleet_speed(f.ships)))
            if eta <= RUSH_HOME_ETA_MAX:
                total_rush += int(f.ships); min_eta = min(min_eta, eta)
    return total_rush >= RUSH_FLEET_MIN, total_rush, min_eta

def detect_enemy_battles(arrivals, enemy_planets, player):
    battles = []
    for target in enemy_planets:
        for eta, o, s in arrivals.get(target.id, []):
            if o in (-1, player) or o == target.owner: continue
            if int(s) <= 0: continue
            eta_i    = int(math.ceil(eta))
            garrison = target.ships + target.production * eta_i
            survivor = max(0, int(s) - int(garrison))
            defender = max(0, int(garrison) - int(s))
            post_owner = o if int(s) > garrison else target.owner
            post_ships = survivor if int(s) > garrison else defender
            if post_ships < GANG_WEAK_THRESH:
                battles.append(dict(target_id=target.id, battle_turn=eta_i,
                                    post_ships=post_ships, post_owner=post_owner))
    return battles

def detect_enemy_crashes(arrivals, player):
    crashes = []
    for tid, arr in arrivals.items():
        en_ev = [(int(math.ceil(eta)), o, int(s)) for eta,o,s in arr
                 if o not in (-1,player) and s > 0]
        en_ev.sort()
        for i in range(len(en_ev)):
            ea, oa, sa = en_ev[i]
            for j in range(i+1, len(en_ev)):
                eb, ob, sb = en_ev[j]
                if oa == ob: continue
                if abs(ea-eb) > CRASH_ETA_WIN: break
                if sa + sb < CRASH_MIN_SHIPS: continue
                crashes.append(dict(target_id=tid, crash_turn=max(ea,eb)))
    return crashes

def detect_kill_shot(my_total, enemy_planets):
    if not enemy_planets: return set()
    total_en = sum(int(p.ships) for p in enemy_planets)
    if my_total < total_en * 1.80: return set()
    return {p.id for p in enemy_planets}

def find_enemy_home_planet(my_home, all_planets, player):
    """
    v7 NEW: In 2P diagonal start, enemy home is at ~(100-x, 100-y).
    Find the enemy planet closest to that predicted position.
    """
    ex = BOARD - my_home.x; ey = BOARD - my_home.y
    enemy_ps = [p for p in all_planets if p.owner not in (-1, player)]
    if not enemy_ps: return None
    return min(enemy_ps, key=lambda p: dist(p.x, p.y, ex, ey))

def next_comet_spawn(step):
    """v7 NEW: How many turns until next comet spawn?"""
    for cs in sorted(COMET_SPAWN_TURNS):
        if cs > step: return cs - step
    return 999

# ════════════════════════════════════════════════════════
# § 7  WORLD MODEL
# ════════════════════════════════════════════════════════

class WorldModel:
    def __init__(self, player, step, planets, fleets, init_by_id, ang_vel, comets, comet_ids):
        self.player     = player; self.step = step
        self.planets    = planets; self.fleets = fleets
        self.init_by_id = init_by_id; self.ang_vel = ang_vel
        self.comets     = comets; self.comet_ids = set(comet_ids)

        self.by_id           = {p.id: p for p in planets}
        self.my_planets      = [p for p in planets if p.owner == player]
        self.enemy_planets   = [p for p in planets if p.owner not in (-1, player)]
        self.neutral_planets = [p for p in planets if p.owner == -1]
        self.static_neutrals = [p for p in self.neutral_planets if is_static_planet(p)]

        self.num_players  = count_players(planets, fleets)
        self.remaining    = max(1, TOTAL_STEPS - step)
        self.is_early     = step < EARLY_LIMIT
        self.is_opening   = step < OPENING_LIMIT
        self.is_late      = self.remaining < LATE_REMAINING
        self.is_very_late = self.remaining < VERY_LATE_REMAINING
        self.is_total_war = self.remaining < TOTAL_WAR_REMAINING
        self.is_endgame   = self.remaining < ENDGAME_REMAINING
        self.is_ffa       = self.num_players >= 4
        self.is_hoarding  = self.remaining < HOARD_REMAINING

        self.owner_strength = defaultdict(int)
        self.owner_prod     = defaultdict(int)
        for p in planets:
            if p.owner != -1:
                self.owner_strength[p.owner] += int(p.ships)
                self.owner_prod[p.owner]     += int(p.production)
        for f in fleets: self.owner_strength[f.owner] += int(f.ships)

        self.my_total    = self.owner_strength.get(player, 0)
        self.enemy_total = sum(s for o,s in self.owner_strength.items() if o != player)
        self.max_enemy   = max((s for o,s in self.owner_strength.items() if o != player), default=0)
        self.my_prod     = self.owner_prod.get(player, 0)
        self.enemy_prod  = sum(s for o,s in self.owner_prod.items() if o != player)

        eco_ratio = self.my_prod / max(1, self.enemy_prod)
        if eco_ratio >= ECO_EXPAND_THRESH:  self.eco_mode = EcoMode.EXPAND
        elif eco_ratio <= ECO_AGGRO_THRESH: self.eco_mode = EcoMode.AGGRO
        else:                               self.eco_mode = EcoMode.BALANCED

        self.win_ratio           = self.my_total / max(1, self.enemy_total)
        self.is_winning_secure   = self.win_ratio >= WIN_SECURE_RATIO
        self.is_losing_desperate = self.win_ratio <= WIN_DESPERATE_RATIO
        self.prod_lead           = self.my_prod / max(1, self.enemy_prod) 

        self.is_rush, self.rush_ships, self.rush_eta = detect_rush(
            fleets, self.my_planets, player, step)
        self._weakest     = weakest_enemy_owner(self.enemy_planets, self.owner_strength, self.owner_prod)
        self._weakest_str = self.owner_strength.get(self._weakest, 0) if self._weakest else 0
        self._deny_target = highest_prod_enemy_planet(self.enemy_planets, self.owner_strength)

        self.arrivals  = build_arrival_ledger(fleets, planets)
        self.timelines = {p.id: simulate_timeline(p, self.arrivals[p.id], player, HORIZON)
                          for p in planets}

        self.indirect_map  = {p.id: indirect_features(p, planets, player) for p in planets}
        self.vuln_ids      = detect_vulnerable_planets(fleets, self.enemy_planets, player)
        self.gateway_map   = {p.id: compute_gateway_value(p, self.enemy_planets)  for p in planets}
        self.frontier_map  = {p.id: compute_frontier_value(p, self.enemy_planets) for p in planets}
        self.cluster_map   = {p.id: compute_cluster_bonus(p, self.my_planets)     for p in planets}
        self.kill_shot_ids = detect_kill_shot(self.my_total, self.enemy_planets)

        if self.my_planets and not self.is_ffa:
            my_home = max(self.my_planets, key=lambda p: int(p.ships))
            self._enemy_home = find_enemy_home_planet(my_home, planets, player)
        else:
            self._enemy_home = None

        self.next_comet = next_comet_spawn(step)

        self.en_fleet_to_my = defaultdict(list)
        for f in fleets:
            if f.owner == player or f.owner == -1: continue
            tp, eta = fleet_target_planet(f, planets)
            if tp is not None and tp.owner == player:
                self.en_fleet_to_my[tp.id].append((eta, f.owner, int(f.ships)))

        self.my_active_attack_targets = set()
        for f in fleets:
            if f.owner != player: continue
            tp, _ = fleet_target_planet(f, planets)
            if tp is not None and tp.owner != player:
                self.my_active_attack_targets.add(tp.id)

        self.total_ships = sum(int(p.ships) for p in planets) + sum(int(f.ships) for f in fleets)
        self.total_prod  = sum(int(p.production) for p in planets)
        self._shot_cache = {}; self._probe_cache = {}
        self._bprobe_cache = {}; self._need_cache = {}

    def is_static(self, pid):       return is_static_planet(self.by_id[pid])
    def comet_life_left(self, pid): return comet_life(pid, self.comets)
    def inv_left(self, sid, spent): return max(0, int(self.by_id[sid].ships) - spent[sid])

    def plan_shot(self, sid, tid, ships):
        ships = int(ships); key = (sid, tid, ships)
        if key in self._shot_cache: return self._shot_cache[key]
        r = aim_with_prediction(self.by_id[sid], self.by_id[tid], ships,
                                self.init_by_id, self.ang_vel, self.comets, self.comet_ids)
        self._shot_cache[key] = r; return r

    def probe_candidates(self, sid, tid, cap, hints=()):
        cap = max(1, int(cap))
        norm_hints = tuple(int(math.ceil(h)) for h in hints if h is not None)
        key = (sid, tid, cap, norm_hints)
        if key in self._probe_cache: return self._probe_cache[key]
        t  = self.by_id[tid]; ts = max(1, int(math.ceil(t.ships)))
        vals = set(range(1, min(6, cap)+1))
        vals.update({cap, max(1,cap//2), max(1,cap//3), min(cap,PARTIAL_MIN),
                     min(cap,ts+1), min(cap,ts+4), min(cap,ts+8)})
        for h in norm_hints:
            b = max(1, min(cap, h))
            for d in (-2,-1,0,1,2):
                c = b+d
                if 1<=c<=cap: vals.add(c)
        result = sorted(vals); self._probe_cache[key] = result; return result

    def best_probe(self, sid, tid, cap, hints=(), min_t=None, max_t=None,
                   anchor=None, anchor_diff=None):
        cap = max(1, int(cap))
        key = (sid, tid, cap, tuple(int(math.ceil(h)) for h in hints if h is not None),
               min_t, max_t, anchor, anchor_diff)
        if key in self._bprobe_cache: return self._bprobe_cache[key]
        best, bkey = None, None
        for ships in self.probe_candidates(sid, tid, cap, hints=hints):
            aim = self.plan_shot(sid, tid, ships)
            if aim is None: continue
            angle, turns, _, _ = aim
            if min_t is not None and turns < min_t: continue
            if max_t is not None and turns > max_t: continue
            if anchor is not None and anchor_diff is not None and abs(turns-anchor)>anchor_diff: continue
            sk = (turns, ships) if anchor is None else (abs(turns-anchor), turns, ships)
            if bkey is None or sk < bkey: bkey, best = sk, (ships, aim)
        self._bprobe_cache[key] = best; return best

    def _search_cap(self, eval_t):
        return max(32, int(self.total_ships + self.total_prod*max(2,eval_t+2) + 32))

    def min_ships_to_own_by(self, tid, eval_t, attacker,
                            arrival_t=None, planned=None, extra=(), upper=None):
        planned = planned or {}
        eval_t  = max(1, int(math.ceil(eval_t)))
        arr_t   = eval_t if arrival_t is None else max(1, int(math.ceil(arrival_t)))
        if arr_t > eval_t:
            return (max(1,int(upper))+1) if upper else self._search_cap(eval_t)+1
        norm_extra = tuple(
            (max(1,int(math.ceil(t))), o, int(s))
            for t,o,s in extra if s>0 and max(1,int(math.ceil(t)))<=eval_t
        )
        ck = None
        if arr_t==eval_t and not planned.get(tid) and not norm_extra:
            ck = (tid, eval_t, attacker); cv = self._need_cache.get(ck)
            if cv is not None: return cv

        def owns_at(ships):
            a = list(self.arrivals.get(tid,[]))
            a += [i for i in planned.get(tid,[]) if i[0]<=eval_t]
            a += [i for i in norm_extra if i[0]<=eval_t]
            a.append((arr_t, attacker, int(ships)))
            tl = simulate_timeline(self.by_id[tid], a, self.player, eval_t)
            o, _ = state_at(tl, eval_t); return o == attacker

        if upper:
            hi = max(1, int(upper))
            if not owns_at(hi): return hi+1
        else:
            o0, s0 = state_at(self.timelines[tid], eval_t)
            if o0 == attacker:
                if ck: self._need_cache[ck] = 0; return 0
            hi  = max(1, int(math.ceil(s0))+1); cap = self._search_cap(eval_t)
            while hi <= cap and not owns_at(hi): hi *= 2
            if hi > cap:
                if not owns_at(cap): return cap+1
                hi = cap
        lo = 1
        while lo < hi:
            mid = (lo+hi)//2
            if owns_at(mid): hi = mid
            else:            lo = mid+1
        if ck: self._need_cache[ck] = lo
        return lo

    def min_ships_to_own_at(self, tid, arr_t, attacker, planned=None, extra=(), upper=None):
        return self.min_ships_to_own_by(tid, arr_t, attacker, arrival_t=arr_t,
                                        planned=planned, extra=extra, upper=upper)

    def proj_state(self, tid, arr_t, planned=None, extra=()):
        planned = planned or {}
        cut = max(1, int(math.ceil(arr_t)))
        if not planned.get(tid) and not extra: return state_at(self.timelines[tid], cut)
        a  = [i for i in self.arrivals.get(tid,[]) if i[0]<=cut]
        a += [i for i in planned.get(tid,[]) if i[0]<=cut]
        a += [i for i in extra if i[0]<=cut]
        return state_at(simulate_timeline(self.by_id[tid], a, self.player, cut), cut)

    def proj_timeline(self, tid, horizon, planned=None, extra=()):
        planned = planned or {}; horizon = max(1, int(math.ceil(horizon)))
        a  = [i for i in self.arrivals.get(tid,[]) if i[0]<=horizon]
        a += [i for i in planned.get(tid,[]) if i[0]<=horizon]
        a += [i for i in extra if i[0]<=horizon]
        return simulate_timeline(self.by_id[tid], a, self.player, horizon)

    def hold_status(self, tid, planned=None):
        tl = self.proj_timeline(tid, HORIZON, planned=planned) \
             if (planned or {}).get(tid) else self.timelines[tid]
        return {k: tl[k] for k in ("keep_needed","fall_turn","holds_full")}

    def reinf_needed(self, tid, arr_t, hold_until, planned=None, upper=None):
        planned    = planned or {}
        tgt        = self.by_id[tid]
        arr_t      = max(1, int(math.ceil(arr_t)))
        hold_until = max(arr_t, int(math.ceil(hold_until)))
        if tgt.owner != self.player:
            return self.min_ships_to_own_by(tid, hold_until, self.player,
                                            arrival_t=arr_t, planned=planned, upper=upper)
        def holds(ships):
            tl = self.proj_timeline(tid, hold_until, planned=planned,
                                    extra=((arr_t, self.player, int(ships)),))
            for t in range(arr_t, hold_until+1):
                if tl["owner_at"].get(t) != self.player: return False
            return True
        if upper:
            hi = max(1, int(upper))
            if not holds(hi): return hi+1
        else:
            hi = 1; cap = self._search_cap(hold_until)
            while hi<=cap and not holds(hi): hi *= 2
            if hi>cap:
                if not holds(cap): return cap+1
                hi = cap
        lo = 1
        while lo < hi:
            mid = (lo+hi)//2
            if holds(mid): hi = mid
            else:          lo = mid+1
        return lo

# ════════════════════════════════════════════════════════
# § 8  STRATEGY LAYER
# ════════════════════════════════════════════════════════

def p_dist(a, b): return math.hypot(a.x-b.x, a.y-b.y)

def nearest_to(target, sources, k):
    if len(sources) <= k: return sources
    return sorted(sources, key=lambda s:(p_dist(s,target),-int(s.ships),s.id))[:k]

def build_modes(world):
    dom = (world.my_total - world.enemy_total) / max(1, world.my_total+world.enemy_total)
    behind     = dom < BEHIND_DOM
    ahead      = dom > AHEAD_DOM
    dominating = ahead or (world.max_enemy>0 and world.my_total > world.max_enemy*1.25)
    finishing  = (dom > FINISH_DOM and world.my_prod > world.enemy_prod*FINISH_PROD_R
                  and world.step > 80)
    mm = 1.0
    if ahead:     mm += AHEAD_MRG_B
    if behind:    mm -= BEHIND_MRG_P
    if finishing: mm += FINISH_MRG_B
    if world.is_winning_secure:   mm *= WIN_SECURE_MARGIN_M
    if world.is_losing_desperate: mm *= WIN_DESPERATE_RISK_M
    return dict(dom=dom, behind=behind, ahead=ahead,
                dominating=dominating, finishing=finishing, mm=mm)

def compute_pressure_mult(world, planned_target_ids):
    total_fronts = len(world.my_active_attack_targets) + len(set(planned_target_ids))
    if total_fronts < PRESSURE_FRONT_MIN: return 1.0
    extra = total_fronts - PRESSURE_FRONT_MIN
    return min(PRESSURE_MAX_MULT, 1.0 + extra * PRESSURE_BONUS_PER)

def build_policy(world, deadline=None):
    def expired(): return deadline and time.perf_counter() > deadline

    iw = {pid: f*IND_FRIENDLY_W + n*IND_NEUTRAL_W + e*IND_ENEMY_W
          for pid,(f,n,e) in world.indirect_map.items()}

    rtm = {}
    for target in world.planets:
        if expired(): break
        if target.owner == world.player: continue
        my_src = nearest_to(target, world.my_planets,    REACT_MY_TOP_K)
        en_src = nearest_to(target, world.enemy_planets, REACT_EN_TOP_K)
        my_t   = min((travel_time(p.x,p.y,p.radius,target.x,target.y,target.radius,max(1,int(p.ships)))
                      for p in my_src), default=10**9)
        en_t   = min((travel_time(p.x,p.y,p.radius,target.x,target.y,target.radius,max(1,int(p.ships)))
                      for p in en_src), default=10**9)
        rtm[target.id] = (my_t, en_t)

    dom = (world.my_total-world.enemy_total) / max(1, world.my_total+world.enemy_total)
    reserve = {}; budget = {}

    for planet in world.my_planets:
        if expired(): break
        tl = world.timelines[planet.id]; exact = tl["keep_needed"]
        threats = []
        for en in nearest_to(planet, world.enemy_planets, PROACT_EN_TOP_K):
            aim = world.plan_shot(en.id, planet.id, max(1, int(en.ships)))
            if aim is None: continue
            eta = aim[1]
            if eta > MULTI_PROACT_HOR: continue
            threats.append((eta, int(en.ships)))
        threats.sort()
        best_stack = 0; l, running = 0, 0
        for r in range(len(threats)):
            running += threats[r][1]
            while threats[r][0]-threats[l][0] > MULTI_STACK_WIN:
                running -= threats[l][1]; l += 1
            best_stack = max(best_stack, running)
        proact = int(best_stack * MULTI_PROACT_RATIO)
        for eta, s in threats:
            if eta <= PROACT_HORIZON: proact = max(proact, int(s * PROACT_RATIO))

        if world.is_rush and world.step < RUSH_DETECT_STEP_MAX: proact = int(proact * 1.5)
        if not world.is_ffa and dom > ONE_V_ONE_DOM_THRESH and not world.is_late:
            exact = int(exact*ONE_V_ONE_AGG_RESERVE); proact = int(proact*ONE_V_ONE_AGG_RESERVE)
        if world.is_winning_secure and not world.is_ffa:
            exact = int(exact*0.78); proact = int(proact*0.78)
        if world.is_total_war:
            exact = min(exact, max(1, exact//2)); proact = min(proact, max(1, proact//2))
        if world.is_hoarding: 
            exact = int(planet.ships * 0.15); proact = 0

        reserve[planet.id] = min(int(planet.ships), max(exact, proact))
        budget[planet.id]  = max(0, int(planet.ships) - reserve[planet.id])

    return dict(iw=iw, rtm=rtm, reserve=reserve, budget=budget)

def react_times(tid, policy): return policy["rtm"].get(tid, (10**9, 10**9))

def is_safe_neutral(t, policy):
    if t.owner != -1: return False
    my_t, en_t = react_times(t.id, policy); return my_t <= en_t - SAFE_NEUTRAL_MARGIN

def is_contested(t, policy):
    if t.owner != -1: return False
    my_t, en_t = react_times(t.id, policy); return abs(my_t-en_t) <= CONTESTED_NEUTRAL_MARGIN

def can_race_to(t, policy):
    if t.owner != -1: return False
    my_t, en_t = react_times(t.id, policy); return en_t - my_t >= RACE_MIN_ADVANTAGE

def open_filter(target, arr_t, needed, src_cap, world, policy):
    if not world.is_opening or target.owner != -1: return False
    if target.id in world.comet_ids or world.is_static(target.id): return False
    my_t, en_t = react_times(target.id, policy); gap = en_t - my_t
    if (target.production >= SAFE_OPEN_PROD_TH and arr_t <= SAFE_OPEN_TURN_LIM
            and gap >= SAFE_NEUTRAL_MARGIN): return False
    if world.is_ffa:
        affordable = needed <= max(PARTIAL_MIN, int(src_cap*FFA_ROT_SEND_RATIO))
        if affordable and arr_t <= FFA_ROT_TURN_LIM and gap >= FFA_ROT_REACT_GAP: return False
        return True
    return arr_t > ROT_OPEN_MAX_TURNS or target.production <= ROT_OPEN_LOW_PROD

def target_value(target, arr_t, mission, world, modes, policy):
    turns_profit = max(1, world.remaining - arr_t)
    if target.id in world.comet_ids:
        life = world.comet_life_left(target.id)
        turns_profit = max(0, min(turns_profit, life - arr_t))
        if turns_profit <= 0: return -1.0

    prod_score = (target.production ** PROD_EXP) * turns_profit
    val = prod_score + policy["iw"][target.id] * turns_profit * INDIRECT_SCALE

    if world.is_static(target.id):
        val *= STATIC_NEUTRAL_VM if target.owner == -1 else STATIC_HOSTILE_VM
    elif world.is_opening: val *= ROT_OPEN_VM

    if target.owner not in (-1, world.player):
        val *= OPEN_HOSTILE_VM if world.is_opening else HOSTILE_VM

    if target.owner == -1:
        if   is_safe_neutral(target, policy): val *= SAFE_NEUTRAL_VM
        elif is_contested(target, policy):    val *= CONTESTED_NEUTRAL_VM
        if   can_race_to(target, policy):     val *= RACE_WIN_VM
        if   world.is_early:                  val *= EARLY_NEUTRAL_VM

    if target.id in world.comet_ids: val *= COMET_VM

    mv = {"snipe":SNIPE_VM,"swarm":SWARM_VM,"reinforce":REINFORCE_VM,
          "crash_exploit":CRASH_VM,"gang_up":GANG_UP_VM}
    val *= mv.get(mission, 1.0)

    if target.id in world.vuln_ids:      val *= EXPOSED_VM
    val *= world.gateway_map.get(target.id, 1.0)
    val *= world.frontier_map.get(target.id, 1.0)
    val *= world.cluster_map.get(target.id, 1.0)
    if target.id in world.kill_shot_ids: val *= KILL_SHOT_VM

    if world.step < OPENING_BOOK_TURNS:
        if target.owner == -1 and world.is_static(target.id):
            val *= OPENING_STATIC_BOOST
        if (target.owner == -1 and dist(target.x, target.y, CENTER_X, CENTER_Y) < 28):
            val *= OPENING_DIAG_BOOST

    if world.eco_mode == EcoMode.EXPAND:
        if   target.owner == -1:           val *= ECO_EXPAND_NEUTRAL_VM
        elif target.owner != world.player: val *= ECO_EXPAND_HOSTILE_VM
    elif world.eco_mode == EcoMode.AGGRO:
        if target.owner not in (-1, world.player):
            val *= ECO_AGGRO_HOSTILE_VM
            if target.production >= PROD_DENY_THRESHOLD: val *= 1.30
        elif target.owner == -1: val *= ECO_AGGRO_NEUTRAL_VM

    if world.is_rush and target.owner not in (-1, world.player): val *= 1.45
    if (target.owner not in (-1, world.player) and target.production >= PROD_DENY_THRESHOLD
            and world._deny_target and target.id == world._deny_target.id):
        val *= PROD_DENY_VM

    if   world.is_hoarding:  val += max(0, target.ships) * HOARD_SHIP_W
    elif world.is_very_late: val += max(0, target.ships) * VERY_LATE_SHIP_W
    elif world.is_late:      val += max(0, target.ships) * LATE_SHIP_W
    elif world.is_endgame:   val += max(0, target.ships) * 0.50

    if target.owner not in (-1, world.player):
        en_str = world.owner_strength.get(target.owner, 0)
        if en_str <= WEAK_THRESH: val += ELIM_BONUS
        if world._weakest and target.owner == world._weakest:
            val *= WEAKEST_VM_FFA if world.is_ffa else WEAKEST_VM_1V1

    if (world._enemy_home and target.id == world._enemy_home.id
            and world.step < 120 and not world.is_ffa):
        val *= 1.30

    if modes["finishing"]  and target.owner not in (-1, world.player): val *= FINISH_HOSTILE_VM
    if modes["behind"]     and target.owner==-1 and not world.is_static(target.id): val *= BEHIND_ROT_VM
    if modes["behind"]     and is_safe_neutral(target, policy): val *= 1.14
    if modes["dominating"] and is_contested(target, policy):    val *= 0.86

    return val

def preferred_send(target, needed, arr_t, cap, world, modes, policy, distance=None):
    send = max(needed, int(math.ceil(needed * modes["mm"])))
    m = 0
    if target.owner == -1:
        m += min(NEUTRAL_MARGIN_CAP, NEUTRAL_MARGIN_BASE + target.production * NEUTRAL_MARGIN_PROD_W)
    else:
        m += min(HOSTILE_MARGIN_CAP, HOSTILE_MARGIN_BASE + target.production * HOSTILE_MARGIN_PROD_W)
    if world.is_static(target.id): m += STATIC_MARGIN
    if is_contested(target, policy): m += CONTESTED_MARGIN
    if world.is_ffa: m += FFA_MARGIN
    if arr_t > LONG_TRAVEL_START: m += min(LONG_TRAVEL_CAP, arr_t // LONG_TRAVEL_DIV)
    if target.id in world.comet_ids: m = max(0, m - COMET_MARGIN_RELIEF)
    if modes["finishing"] and target.owner not in (-1, world.player): m += FINISH_SEND_BONUS
    if target.id in world.vuln_ids: m = max(0, m-3)
    if world.is_ffa and world._weakest and target.owner==world._weakest: m = max(0, m-2)
    base = min(cap, send + m)
    d = distance if distance is not None else 30.0
    prod_proxy = target.production if target.owner == -1 else target.production * 2
    return speed_optimal_send(base, cap, d, prod_proxy)

def score_mods(base, target, mission, world, policy, pressure_mult=1.0):
    s = base
    if world.is_static(target.id): s *= STATIC_SCORE_M
    if world.is_early and target.owner==-1 and world.is_static(target.id): s *= EARLY_STATIC_SCORE_M
    if world.is_ffa and target.owner==-1 and not world.is_static(target.id): s *= FFA_ROT_SCORE_M
    if (len(world.static_neutrals) >= DENSE_STATIC_THRESH
            and target.owner==-1 and not world.is_static(target.id)): s *= DENSE_ROT_SCORE_M
    if mission == "snipe": s *= SNIPE_SCORE_M
    elif mission in ("swarm","gang_up"): s *= SWARM_SCORE_M
    elif mission == "crash_exploit": s *= CRASH_SCORE_M
    if target.id in world.vuln_ids: s *= EXPOSED_SCORE_M
    if target.owner not in (-1, world.player) and world._weakest==target.owner: s *= WEAKEST_SCORE_M
    if target.owner==-1 and can_race_to(target, policy): s *= RACE_SCORE_MULT
    s *= pressure_mult; return s

def candidate_valid(target, turns, world, buf):
    if turns > world.remaining - buf: return False
    if target.id in world.comet_ids:
        life = world.comet_life_left(target.id)
        if turns >= life or turns > COMET_MAX_CHASE: return False
    return True

# ════════════════════════════════════════════════════════
# § 9  SETTLE PLAN (ITERATIVE CONVERGENCE)
# ════════════════════════════════════════════════════════

def settle_plan(src, target, cap, send_guess, world, planned, modes, policy,
                mission="capture", eval_fn=None, anchor=None, anchor_tol=None,
                max_iter=4, distance=None):
    if cap < 1: return None
    eval_fn    = eval_fn or (lambda t: t)
    anchor_tol = anchor_tol if anchor_tol is not None else (1 if mission=="snipe" else None)
    seed       = max(1, min(cap, int(send_guess)))
    tested = {}; order = []

    def evaluate(send):
        send = max(1, min(cap, int(send)))
        if send in tested: return tested[send]
        aim = world.plan_shot(src.id, target.id, send)
        if aim is None: tested[send]=None; return None
        angle, turns, _, _ = aim
        if mission=="crash_exploit" and anchor and turns < anchor:
            tested[send]=None; return None
        et = int(math.ceil(eval_fn(turns)))
        if et < turns: tested[send]=None; return None
        need = world.min_ships_to_own_by(target.id, et, world.player,
                                         arrival_t=turns, planned=planned, upper=cap)
        if need<=0 or need>cap: tested[send]=None; return None
        if mission in ("snipe","crash_exploit"): desired = need
        elif mission == "rescue":
            desired = min(cap, max(need, need+DEF_SEND_MARGIN+target.production*DEF_SEND_PROD_W))
        else:
            desired = min(cap, max(need, preferred_send(target, need, turns, cap, world, modes, policy, distance)))
        result = (angle, turns, et, need, send, desired)
        tested[send]=result; order.append(send); return result

    cands = sorted(world.probe_candidates(src.id, target.id, cap, hints=(seed,)),
                   key=lambda s:(abs(s-seed), s))
    cur = None
    for s in cands:
        r = evaluate(s)
        if r is None: continue
        if anchor and anchor_tol and abs(r[1]-anchor)>anchor_tol: continue
        cur = s; break
    if cur is None: return None
    for _ in range(max_iter):
        r = evaluate(cur)
        if r is None: break
        angle, turns, et, need, actual, desired = r
        if desired == actual:
            if anchor and anchor_tol and abs(turns-anchor)>anchor_tol: return None
            if mission=="rescue" and turns>et: return None
            return angle, turns, et, need, actual
        nxt = max(1, min(cap, int(desired)))
        if nxt in tested: cur=nxt; break
        cur = nxt
    seen = set()
    for s in sorted(order, key=lambda s:(
        0 if not anchor or anchor_tol is None else abs(tested[s][1]-anchor),
        abs(s-seed), tested[s][1], s
    )):
        if s in seen: continue; seen.add(s)
        r = tested.get(s)
        if r is None: continue
        angle, turns, et, need, actual, _ = r
        if actual < need: continue
        if anchor and anchor_tol and abs(turns-anchor)>anchor_tol: continue
        if mission=="rescue" and turns>et: continue
        return angle, turns, et, need, actual
    return None

def settle_reinf(src, target, cap, seed, world, planned, hold_until, max_arr, max_iter=4):
    if cap < 1: return None
    tested = {}; order = []
    def evaluate(send):
        send = max(1,min(cap,int(send)))
        if send in tested: return tested[send]
        aim = world.plan_shot(src.id, target.id, send)
        if aim is None: tested[send]=None; return None
        angle,turns,_,_ = aim
        if turns>max_arr: tested[send]=None; return None
        need = world.reinf_needed(target.id, turns, hold_until, planned=planned, upper=cap)
        if need<=0 or need>cap: tested[send]=None; return None
        desired = min(cap, need+REINF_SAFETY)
        r=(angle,turns,hold_until,need,send,desired); tested[send]=r; order.append(send); return r
    cands = sorted(world.probe_candidates(src.id,target.id,cap,hints=(seed,)),
                   key=lambda s:(abs(s-seed),s))
    cur = None
    for s in cands:
        r=evaluate(s)
        if r: cur=s; break
    if cur is None: return None
    for _ in range(max_iter):
        r=evaluate(cur)
        if r is None: break
        angle,turns,_,need,actual,desired = r
        if desired==actual: return angle,turns,hold_until,need,actual
        nxt=max(1,min(cap,int(desired)))
        if nxt in tested: cur=nxt; break
        cur=nxt
    for s in sorted(order,key=lambda s:(abs(s-seed),tested[s][1],s)):
        r=tested.get(s)
        if r is None: continue
        angle,turns,_,need,actual,_ = r
        if actual<need or turns>max_arr: continue
        return angle,turns,hold_until,need,actual
    return None

# ════════════════════════════════════════════════════════
# § 10  MISSION BUILDERS
# ════════════════════════════════════════════════════════

def build_intercept_missions(world, planned, modes, policy):
    if not INTERCEPT_ENABLED: return []
    missions = []
    for my_pid, fleet_list in world.en_fleet_to_my.items():
        target = world.by_id[my_pid]
        for en_eta, en_owner, en_ships in sorted(fleet_list, key=lambda x: x[0]):
            if en_eta > INTERCEPT_ETA_MAX: continue
            garrison_at_eta = target.ships + target.production * en_eta
            deficit = max(0, en_ships - garrison_at_eta + 1)
            if deficit <= 0: continue
            for src in world.my_planets:
                if src.id == my_pid: continue
                cap = policy["budget"].get(src.id, 0)
                if cap < deficit: continue
                probe = world.best_probe(src.id, my_pid, cap,
                                         hints=(deficit, deficit+5), max_t=en_eta-1)
                if probe is None: continue
                _, rough = probe
                if rough[1] >= en_eta: continue
                plan = settle_reinf(src, target, cap, probe[0], world, planned,
                                    en_eta+10, en_eta-1)
                if plan is None: continue
                angle, turns, _, need, send = plan
                if turns >= en_eta: continue
                sv  = max(1, world.remaining - en_eta)
                val = target.production * sv * DEF_FRONTIER_M
                sc  = val / (send + turns*DEF_TURN_W + 1.0) * 1.7
                opt = ShotOption(sc, src.id, my_pid, angle, turns, need, send, "reinforce", en_eta)
                missions.append(Mission("reinforce", sc, my_pid, en_eta, [opt])); break
    return missions

def build_rescue_missions(world, planned, modes, policy):
    missions = []
    for target in world.my_planets:
        ft = world.timelines[target.id]["fall_turn"]
        if ft is None or ft > DEF_LOOKAHEAD: continue
        for src in world.my_planets:
            if src.id==target.id: continue
            cap = policy["budget"].get(src.id,0)
            if cap < PARTIAL_MIN: continue
            probe = world.best_probe(src.id, target.id, cap,
                                     hints=(target.production+DEF_SEND_MARGIN+2,), max_t=ft)
            if probe is None: continue
            plan = settle_plan(src, target, cap, probe[0], world, planned, modes, policy,
                               mission="rescue", eval_fn=lambda _,f=ft:f, anchor=ft)
            if plan is None: continue
            angle,turns,_,need,send = plan
            sv  = max(1, world.remaining - ft)
            val = target.production*sv + max(0,target.ships)*DEF_SHIP_VALUE
            if world.enemy_planets and nearest_dist(target.x,target.y,world.enemy_planets)<22:
                val *= DEF_FRONTIER_M
            sc = val/(send+turns*DEF_TURN_W+1.0)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "rescue", ft)
            missions.append(Mission("rescue", sc, target.id, ft, [opt]))
    return missions

def build_reinf_missions(world, planned, modes, policy, inv_left_fn):
    if not REINF_ENABLED or world.remaining < REINF_MIN_FUTURE: return []
    missions = []
    for target in world.my_planets:
        ft = world.timelines[target.id]["fall_turn"]
        if ft is None or target.production < REINF_MIN_PROD: continue
        hold_until = min(HORIZON, ft + REINF_LOOKAHEAD); max_arr = min(ft, REINF_MAX_TRAVEL)
        for src in world.my_planets:
            if src.id==target.id: continue
            cap = min(inv_left_fn(src.id), int(src.ships*REINF_MAX_SRC_FRAC))
            if cap < PARTIAL_MIN: continue
            probe = world.best_probe(src.id, target.id, cap,
                                     hints=(target.production+REINF_SAFETY+2,), max_t=max_arr)
            if probe is None: continue
            plan = settle_reinf(src, target, cap, probe[0], world, planned, hold_until, max_arr)
            if plan is None: continue
            angle,turns,_,need,send = plan
            sv  = max(1, world.remaining - hold_until)
            val = target.production*sv + max(0,target.ships)*DEF_SHIP_VALUE
            if world.enemy_planets and nearest_dist(target.x,target.y,world.enemy_planets)<22:
                val *= DEF_FRONTIER_M
            val *= REINFORCE_VM; sc = val/(send+turns*REINF_TURN_W+1.0)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "reinforce", hold_until)
            missions.append(Mission("reinforce", sc, target.id, ft, [opt]))
    return missions

def build_recap_missions(world, planned, modes, policy):
    missions = []
    for target in world.my_planets:
        ft = world.timelines[target.id]["fall_turn"]
        if ft is None or ft > DEF_LOOKAHEAD: continue
        for src in world.my_planets:
            if src.id==target.id: continue
            cap = policy["budget"].get(src.id,0)
            if cap < PARTIAL_MIN: continue
            probe = world.best_probe(src.id, target.id, cap,
                                     hints=(target.production+DEF_SEND_MARGIN+2,),
                                     min_t=ft+1, max_t=ft+RECAP_LOOKAHEAD)
            if probe is None: continue
            plan = settle_plan(src, target, cap, probe[0], world, planned, modes, policy,
                               mission="capture")
            if plan is None: continue
            angle,turns,_,need,send = plan
            if turns<=ft or turns-ft>RECAP_LOOKAHEAD: continue
            sv  = max(1, world.remaining - turns)
            val = (RECAP_PROD_W*target.production*sv + RECAP_IMMED_W*max(0,target.ships))
            if world.enemy_planets and nearest_dist(target.x,target.y,world.enemy_planets)<22:
                val *= RECAP_FRONTIER_M
            val *= RECAP_VM_MULT; sc = val/(send+turns*RECAP_TURN_W+1.0)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "recapture", ft)
            missions.append(Mission("recapture", sc, target.id, turns, [opt]))
    return missions

def build_elimination_missions(world, planned, modes, policy, pressure_mult):
    if world._weakest is None: return []
    if world._weakest_str > world.my_total*0.92: return []
    other_en = [s for o,s in world.owner_strength.items() if o not in (world.player, world._weakest)]
    if other_en and world._weakest_str > min(other_en)*0.95: return []
    wk_planets = [p for p in world.enemy_planets if p.owner==world._weakest]
    if not wk_planets: return []
    mult = 1.72 if world.is_ffa else 1.45
    missions = []
    for target in wk_planets:
        for src in world.my_planets:
            cap = policy["budget"].get(src.id,0)
            if cap<PARTIAL_MIN: continue
            probe = world.best_probe(src.id, target.id, cap, hints=(int(target.ships)+1,))
            if probe is None: continue
            _,rough = probe
            if not candidate_valid(target, rough[1], world, LATE_BUFFER): continue
            d  = p_dist(src, target)
            sg = preferred_send(target, probe[0], rough[1], cap, world, modes, policy, distance=d)
            plan = settle_plan(src, target, cap, sg, world, planned, modes, policy,
                               mission="capture", distance=d)
            if plan is None: continue
            angle,turns,_,need,send = plan
            if not candidate_valid(target, turns, world, LATE_BUFFER) or send<need: continue
            val = target_value(target, turns, "capture", world, modes, policy)
            if val<=0: continue
            sc  = score_mods(val*mult/(send+turns*ATTACK_TURN_W+1.0), target, "capture",
                             world, policy, pressure_mult)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "capture")
            missions.append(Mission("single", sc, target.id, turns, [opt]))
    return missions

def build_deny_missions(world, planned, modes, policy, pressure_mult):
    if world._deny_target is None: return []
    target = world._deny_target
    if target.owner==world.player or target.production<PROD_DENY_THRESHOLD: return []
    missions = []
    for src in world.my_planets:
        cap = policy["budget"].get(src.id,0)
        if cap<PARTIAL_MIN: continue
        probe = world.best_probe(src.id, target.id, cap, hints=(int(target.ships)+1,))
        if probe is None: continue
        _,rough = probe
        if not candidate_valid(target, rough[1], world, LATE_BUFFER): continue
        d  = p_dist(src, target)
        sg = preferred_send(target, probe[0], rough[1], cap, world, modes, policy, distance=d)
        plan = settle_plan(src, target, cap, sg, world, planned, modes, policy,
                           mission="capture", distance=d)
        if plan is None: continue
        angle,turns,_,need,send = plan
        if not candidate_valid(target, turns, world, LATE_BUFFER) or send<need: continue
        val = target_value(target, turns, "capture", world, modes, policy)
        if val<=0: continue
        sc  = score_mods(val*PROD_DENY_VM/(send+turns*ATTACK_TURN_W+1.0), target, "capture",
                         world, policy, pressure_mult)
        opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "capture")
        missions.append(Mission("single", sc, target.id, turns, [opt]))
    return missions

def build_gang_up_missions(world, planned, modes, policy, pressure_mult):
    missions = []
    for b in detect_enemy_battles(world.arrivals, world.enemy_planets, world.player):
        target = world.by_id[b["target_id"]]
        if target.owner==world.player: continue
        desired = b["battle_turn"] + GANG_POST_DELAY
        for src in world.my_planets:
            cap = policy["budget"].get(src.id,0)
            if cap<PARTIAL_MIN: continue
            hint  = max(3, int(b["post_ships"])+3)
            probe = world.best_probe(src.id, target.id, cap,
                                     hints=(hint,int(target.ships)+1),
                                     anchor=desired, anchor_diff=GANG_ETA_WIN)
            if probe is None: continue
            plan = settle_plan(src, target, cap, probe[0], world, planned, modes, policy,
                               mission="capture", eval_fn=lambda t,da=desired:max(t,da),
                               anchor=desired, anchor_tol=GANG_ETA_WIN)
            if plan is None: continue
            angle,turns,_,need,send = plan
            if not candidate_valid(target, turns, world, LATE_BUFFER): continue
            val = target_value(target, turns, "gang_up", world, modes, policy)
            if val<=0: continue
            sc  = score_mods(val/(send+turns*ATTACK_TURN_W+1.0), target, "gang_up",
                             world, policy, pressure_mult)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "capture", desired)
            missions.append(Mission("single", sc, target.id, turns, [opt]))
    return missions

def build_race_missions(world, planned, modes, policy, pressure_mult):
    missions = []
    for target in world.neutral_planets:
        if target.id in world.comet_ids: continue
        my_t, en_t = react_times(target.id, policy)
        if en_t==10**9 or en_t-my_t < RACE_MIN_ADVANTAGE: continue
        for src in world.my_planets:
            src_cap = policy["budget"].get(src.id,0)
            if src_cap<PARTIAL_MIN: continue
            probe = world.best_probe(src.id, target.id, src_cap,
                                     hints=(int(target.ships)+1,),
                                     max_t=en_t+RACE_MARGIN_TURNS+1)
            if probe is None: continue
            _,rough = probe
            if rough[1]>en_t: continue
            d = p_dist(src, target)
            plan = settle_plan(src, target, src_cap, probe[0], world, planned, modes, policy,
                               mission="capture", distance=d)
            if plan is None: continue
            angle,turns,_,need,send = plan
            if turns>=en_t or not candidate_valid(target, turns, world, LATE_BUFFER): continue
            val = target_value(target, turns, "capture", world, modes, policy)
            if val<=0: continue
            sc  = score_mods(val/(send+turns*ATTACK_TURN_W+1.0), target, "capture",
                             world, policy, pressure_mult)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "capture")
            missions.append(Mission("single", sc, target.id, turns, [opt]))
    return missions

def build_snipe_missions(world, planned, modes, policy, pressure_mult):
    missions = []
    for target in world.neutral_planets:
        en_etas = sorted({int(math.ceil(eta)) for eta,o,s in world.arrivals.get(target.id,[])
                          if o not in (-1,world.player) and s>0})
        if not en_etas: continue
        for src in world.my_planets:
            src_cap = policy["budget"].get(src.id,0)
            if src_cap<PARTIAL_MIN: continue
            for en_eta in en_etas[:3]:
                probe = world.best_probe(src.id, target.id, src_cap,
                                         hints=(int(target.ships)+1,),
                                         anchor=en_eta, anchor_diff=1)
                if probe is None: continue
                plan = settle_plan(src, target, src_cap, probe[0], world, planned, modes, policy,
                                   mission="snipe", eval_fn=lambda t,ee=en_eta:max(t,ee),
                                   anchor=en_eta)
                if plan is None: continue
                angle,turns,sync_t,need,send = plan
                if target.id in world.comet_ids:
                    life = world.comet_life_left(target.id)
                    if sync_t>=life or sync_t>COMET_MAX_CHASE: continue
                val = target_value(target, sync_t, "snipe", world, modes, policy)
                if val<=0: continue
                sc  = score_mods(val/(send+sync_t*SNIPE_TURN_W+1.0), target, "snipe",
                                 world, policy, pressure_mult)
                opt = ShotOption(sc, src.id, target.id, angle, turns, need, send, "snipe", en_eta)
                missions.append(Mission("snipe", sc, target.id, sync_t, [opt]))
    return missions

def build_crash_missions(world, planned, modes, policy, pressure_mult):
    if not CRASH_ENABLED or not world.is_ffa: return []
    missions = []
    for crash in detect_enemy_crashes(world.arrivals, world.player):
        target = world.by_id[crash["target_id"]]
        if target.owner==world.player: continue
        desired_arr = crash["crash_turn"] + CRASH_DELAY
        for src in world.my_planets:
            cap = policy["budget"].get(src.id,0)
            if cap<PARTIAL_MIN: continue
            probe = world.best_probe(src.id, target.id, cap,
                                     hints=(12,int(target.ships)+1),
                                     anchor=desired_arr, anchor_diff=CRASH_ETA_WIN)
            if probe is None: continue
            plan = settle_plan(src, target, cap, probe[0], world, planned, modes, policy,
                               mission="crash_exploit",
                               eval_fn=lambda t,da=desired_arr:max(t,da),
                               anchor=desired_arr, anchor_tol=CRASH_ETA_WIN)
            if plan is None: continue
            angle,turns,_,need,send = plan
            if not candidate_valid(target, turns, world, LATE_BUFFER): continue
            val = target_value(target, turns, "crash_exploit", world, modes, policy)
            if val<=0: continue
            sc  = score_mods(val/(send+turns*SNIPE_TURN_W+1.0), target, "crash_exploit",
                             world, policy, pressure_mult)
            opt = ShotOption(sc, src.id, target.id, angle, turns, need, send,
                             "crash_exploit", desired_arr)
            missions.append(Mission("crash_exploit", sc, target.id, turns, [opt]))
    return missions

# ════════════════════════════════════════════════════════
# § 11  PLAN MOVES — MASTER CONTROLLER
# ════════════════════════════════════════════════════════

def plan_moves(world, deadline=None):
    def expired():  return deadline and time.perf_counter() > deadline
    def tl():       return (deadline - time.perf_counter()) if deadline else 10**9
    def heavy_ok(): return tl() > HEAVY_MIN_TIME and len(world.planets) <= HEAVY_PLANET_LIM
    def opt_ok():   return tl() > OPT_MIN_TIME

    modes   = build_modes(world)
    policy  = build_policy(world, deadline=deadline)
    planned = defaultdict(list)
    src_opts= defaultdict(list)
    missions= []
    moves   = []
    spent   = defaultdict(int)

    def inv_left(sid):  return world.inv_left(sid, spent)
    def atk_left(sid):  return max(0, policy["budget"].get(sid,0) - spent[sid])

    def push(sid, angle, ships):
        send = min(int(ships), inv_left(sid))
        if send < 1: return 0
        moves.append([sid, float(angle), int(send)]); spent[sid] += send; return send

    def finalize():
        final = []; used = defaultdict(int)
        for sid, angle, ships in moves:
            mx = int(world.by_id[sid].ships) - used[sid]
            s  = min(int(ships), mx)
            if s>=1: final.append([sid, float(angle), int(s)]); used[sid]+=s
        return final

    def live_doomed():
        d = set()
        for p in world.my_planets:
            st = world.hold_status(p.id, planned=planned)
            if (not st["holds_full"] and st["fall_turn"] and
                    st["fall_turn"]<=DOOMED_EVAC_LIMIT and inv_left(p.id)>=DOOMED_MIN_SHIPS):
                d.add(p.id)
        return d

    def time_ok(target, turns):
        buf = VERY_LATE_BUFFER if world.is_very_late else LATE_BUFFER
        return candidate_valid(target, turns, world, buf)

    def get_pressure():
        return compute_pressure_mult(world, list(planned.keys()))

    # ── v7: Ship hoarding mode ───────────────────────────────────
    # In last HOARD_REMAINING turns, don't attack — conserve ships for score
    if world.is_hoarding and not world.kill_shot_ids:
        # Only do kill-shot attacks or defense
        missions += build_intercept_missions(world, planned, modes, policy)
        missions += build_rescue_missions(world, planned, modes, policy)
        # Only kill-shot attacks
        if world.kill_shot_ids:
            pressure = get_pressure()
            missions += build_elimination_missions(world, planned, modes, policy, pressure)
        missions.sort(key=lambda m: -m.score)
        for m in missions:
            if expired(): return finalize()
            _execute_mission(m, world, planned, modes, policy, moves, spent, inv_left, atk_left, push)
        return finalize()

    pressure = get_pressure()

    # ── Phase 1: Defense (Priority 1-4) ──────────────────────────
    missions += build_intercept_missions(world, planned, modes, policy)
    missions += build_rescue_missions(world, planned, modes, policy)
    if heavy_ok():
        missions += build_reinf_missions(world, planned, modes, policy, inv_left)
    missions += build_recap_missions(world, planned, modes, policy)

    # ── Phase 2: Tactics (Priority 5-10) ─────────────────────────
    if heavy_ok():
        missions += build_elimination_missions(world, planned, modes, policy, pressure)
        missions += build_deny_missions(world, planned, modes, policy, pressure)
        missions += build_gang_up_missions(world, planned, modes, policy, pressure)
        missions += build_race_missions(world, planned, modes, policy, pressure)
    missions += build_snipe_missions(world, planned, modes, policy, pressure)

    # ── Phase 3: Single-source + swarm enumeration ───────────────
    for src in world.my_planets:
        if expired(): return finalize()
        src_cap = atk_left(src.id)
        if src_cap <= 0: continue
        for target in world.planets:
            if expired(): return finalize()
            if target.id==src.id or target.owner==world.player: continue
            probe = world.best_probe(src.id, target.id, src_cap, hints=(int(target.ships)+1,))
            if probe is None: continue
            _, rough_aim = probe; rough_t = rough_aim[1]
            if not time_ok(target, rough_t): continue
            gn = world.min_ships_to_own_at(target.id, rough_t, world.player, planned=planned)
            if gn<=0: continue
            if open_filter(target, rough_t, gn, src_cap, world, policy): continue
            d = p_dist(src, target)
            # Swarm partial
            part_cap = min(src_cap, preferred_send(target, gn, rough_t, src_cap, world, modes, policy, d))
            if part_cap >= PARTIAL_MIN:
                p2 = world.best_probe(src.id, target.id, part_cap,
                                      hints=(part_cap, gn, int(target.ships)+1))
                if p2:
                    _, pa = p2
                    if (time_ok(target, pa[1]) and
                            not open_filter(target, pa[1], gn, src_cap, world, policy)):
                        val = target_value(target, pa[1], "swarm", world, modes, policy)
                        if val > 0:
                            pm = get_pressure()
                            sc = score_mods(val/(part_cap+pa[1]*ATTACK_TURN_W+1.0),
                                            target, "swarm", world, policy, pm)
                            src_opts[target.id].append(
                                ShotOption(sc,src.id,target.id,pa[0],pa[1],gn,part_cap,"swarm"))
            # Full single-source
            if gn <= src_cap:
                sg   = preferred_send(target, gn, rough_t, src_cap, world, modes, policy, d)
                plan = settle_plan(src, target, src_cap, sg, world, planned, modes, policy,
                                   mission="capture", distance=d)
                if plan is None: continue
                angle,turns,_,need,send = plan
                if not time_ok(target, turns): continue
                if open_filter(target, turns, need, src_cap, world, policy): continue
                val = target_value(target, turns, "capture", world, modes, policy)
                if val<=0: continue
                pm  = get_pressure()
                sc  = score_mods(val/(send+turns*ATTACK_TURN_W+1.0), target, "capture",
                                 world, policy, pm)
                if send>=need:
                    missions.append(Mission("single", sc, target.id, turns,
                                           [ShotOption(sc,src.id,target.id,angle,turns,need,send)]))

    # ── Phase 4: Swarm assembly ───────────────────────────────────
    for tid, options in src_opts.items():
        if expired(): return finalize()
        if len(options)<2: continue
        target = world.by_id[tid]
        top    = sorted(options, key=lambda x:-x.score)[:MULTI_TOP_K]
        # 2-source
        for i in range(len(top)):
            for j in range(i+1,len(top)):
                a, b = top[i], top[j]
                if a.src_id==b.src_id: continue
                tol = HOSTILE_SWARM_TOL if target.owner not in (-1,world.player) else MULTI_ETA_TOL
                if abs(a.turns-b.turns)>tol: continue
                jt = max(a.turns,b.turns); tc = a.send_cap+b.send_cap
                need = world.min_ships_to_own_at(tid, jt, world.player, planned=planned, upper=tc)
                if need<=0 or a.send_cap>=need or b.send_cap>=need or tc<need: continue
                val = target_value(target, jt, "swarm", world, modes, policy)
                if val<=0: continue
                pm  = get_pressure()
                sc  = score_mods(val/(need+jt*ATTACK_TURN_W+1.0), target, "swarm",
                                 world, policy, pm) * MULTI_PLAN_PEN
                missions.append(Mission("swarm", sc, tid, jt, [a,b]))
        # 3-source
        if (THREE_SRC_ENABLED and heavy_ok()
                and target.owner not in (-1,world.player)
                and int(target.ships)>=THREE_SRC_MIN_SHIPS and len(top)>=3):
            for i in range(len(top)):
                for j in range(i+1,len(top)):
                    for k in range(j+1,len(top)):
                        if expired(): return finalize()
                        trio = [top[i],top[j],top[k]]
                        if len({x.src_id for x in trio})<3: continue
                        ts = [x.turns for x in trio]
                        if max(ts)-min(ts)>THREE_SRC_TOL: continue
                        jt = max(ts); tc = sum(x.send_cap for x in trio)
                        need = world.min_ships_to_own_at(tid,jt,world.player,planned=planned,upper=tc)
                        if need<=0 or tc<need: continue
                        if any(trio[ia].send_cap+trio[ib].send_cap>=need
                               for ia in range(3) for ib in range(ia+1,3)): continue
                        val = target_value(target, jt, "swarm", world, modes, policy)
                        if val<=0: continue
                        pm  = get_pressure()
                        sc  = score_mods(val/(need+jt*ATTACK_TURN_W+1.0), target, "swarm",
                                         world, policy, pm) * THREE_SRC_PEN
                        missions.append(Mission("swarm", sc, tid, jt, trio))

    if heavy_ok():
        missions += build_crash_missions(world, planned, modes, policy, get_pressure())

    missions.sort(key=lambda m: -m.score)

    # ── Phase 5: Execute missions ─────────────────────────────────
    for m in missions:
        if expired(): return finalize()
        _execute_mission(m, world, planned, modes, policy, moves, spent, inv_left, atk_left, push)

    # ── Phase 6: Followup pass ────────────────────────────────────
    if not world.is_very_late and opt_ok():
        for src in world.my_planets:
            if expired(): return finalize()
            sleft = atk_left(src.id)
            if sleft < FOLLOWUP_MIN: continue
            best = None
            for target in world.planets:
                if expired(): return finalize()
                if target.id==src.id or target.owner==world.player: continue
                if target.id in world.comet_ids and target.production<=LOW_COMET_PROD: continue
                probe = world.best_probe(src.id, target.id, sleft, hints=(int(target.ships)+1,))
                if probe is None: continue
                _,ra = probe; et = ra[1]
                if world.is_late and et>world.remaining-LATE_BUFFER: continue
                gn = world.min_ships_to_own_at(target.id, et, world.player,
                                               planned=planned, upper=sleft)
                if gn<=0 or gn>sleft: continue
                if open_filter(target, et, gn, sleft, world, policy): continue
                d  = p_dist(src, target)
                sg = preferred_send(target, gn, et, sleft, world, modes, policy, distance=d)
                if sg<gn: continue
                plan = settle_plan(src, target, sleft, sg, world, planned, modes, policy,
                                   mission="capture", distance=d)
                if plan is None: continue
                _,turns,_,need,send = plan
                if world.is_late and turns>world.remaining-LATE_BUFFER: continue
                if send<need: continue
                val = target_value(target, turns, "capture", world, modes, policy)
                if val<=0: continue
                pm  = get_pressure()
                sc  = score_mods(val/(send+turns*ATTACK_TURN_W+1.0), target, "capture",
                                 world, policy, pm)
                if best is None or sc>best[0]: best=(sc,target,plan,d)
            if best is None: continue
            _,target,plan,d = best
            angle,turns,_,need,send = plan
            sleft = atk_left(src.id)
            if need>sleft: continue
            plan2 = settle_plan(src,target,sleft,min(sleft,send),world,planned,modes,policy,
                                mission="capture",distance=d)
            if plan2 is None: continue
            angle,turns,_,need,send = plan2
            if send<need: continue
            ts = speed_optimal_send(need, sleft, d, target.production)
            if ts >= need: send = ts
            a=push(src.id, angle, send)
            if a>=need: planned[target.id].append((turns,world.player,int(a)))

    # ── Phase 7: Doomed evacuation ────────────────────────────────
    if opt_ok():
        doomed = live_doomed()
        if doomed:
            ft_set = world.enemy_planets or world.static_neutrals or world.neutral_planets
            fd     = {p.id: nearest_dist(p.x,p.y,ft_set) for p in world.my_planets} if ft_set else {}
            for planet in world.my_planets:
                if expired(): return finalize()
                if planet.id not in doomed: continue
                avail = inv_left(planet.id)
                if avail < policy["reserve"].get(planet.id,0): continue
                best_cap = None
                for target in world.planets:
                    if expired(): return finalize()
                    if target.id==planet.id or target.owner==world.player: continue
                    probe = world.best_probe(planet.id,target.id,avail,
                                             hints=(avail,int(target.ships)+1))
                    if probe is None: continue
                    _,pa = probe
                    if pa[1]>world.remaining-2: continue
                    need=world.min_ships_to_own_at(target.id,pa[1],world.player,
                                                   planned=planned,upper=avail)
                    if need<=0 or need>avail: continue
                    plan=settle_plan(planet,target,avail,
                                     min(avail,max(need,int(target.ships)+1)),
                                     world,planned,modes,policy,mission="capture")
                    if plan is None: continue
                    angle,turns,_,pn,send=plan
                    if send<pn: continue
                    sc=target_value(target,turns,"capture",world,modes,policy)/(send+turns+1.0)
                    if target.owner not in(-1,world.player): sc*=1.05
                    if best_cap is None or sc>best_cap[0]: best_cap=(sc,target.id,angle,turns,send)
                if best_cap:
                    _,tid,angle,turns,send=best_cap
                    a=push(planet.id,angle,send)
                    if a>=1: planned[tid].append((turns,world.player,int(a))); continue
                allies=[p for p in world.my_planets if p.id!=planet.id and p.id not in doomed]
                if not allies: continue
                ret=min(allies,key=lambda p:(fd.get(p.id,10**9),p_dist(planet,p)))
                aim=world.plan_shot(planet.id,ret.id,avail)
                if aim: push(planet.id, aim[0], avail)

    # ── Phase 8: Rear logistics ───────────────────────────────────
    if ((world.enemy_planets or world.neutral_planets)
            and len(world.my_planets)>1 and not world.is_late and opt_ok()):
        doomed  = live_doomed()
        ft_set  = world.enemy_planets or world.static_neutrals or world.neutral_planets
        fd      = {p.id: nearest_dist(p.x,p.y,ft_set) for p in world.my_planets}
        safe_fs = [p for p in world.my_planets if p.id not in doomed]
        if safe_fs:
            anchor = min(safe_fs, key=lambda p:fd[p.id])
            ratio  = REAR_RATIO_FFA if world.is_ffa else REAR_RATIO_2P
            if modes["finishing"]: ratio = max(ratio, REAR_RATIO_FFA)
            for rear in sorted(world.my_planets, key=lambda p:-fd[p.id]):
                if expired(): return finalize()
                if rear.id==anchor.id or rear.id in doomed: continue
                if atk_left(rear.id)<REAR_MIN_SHIPS: continue
                if fd[rear.id]<fd[anchor.id]*REAR_DIST_RATIO: continue
                stage=[p for p in safe_fs if p.id!=rear.id and fd[p.id]<fd[rear.id]*REAR_STAGE_PROG]
                if stage: front=min(stage,key=lambda p:p_dist(rear,p))
                else:
                    obj=min(ft_set,key=lambda t:p_dist(rear,t))
                    rem=[p for p in safe_fs if p.id!=rear.id]
                    if not rem: continue
                    front=min(rem,key=lambda p:p_dist(p,obj))
                if front.id==rear.id: continue
                send=int(atk_left(rear.id)*ratio)
                if send<REAR_SEND_MIN: continue
                aim=world.plan_shot(rear.id,front.id,send)
                if aim is None or aim[1]>REAR_MAX_TRAVEL: continue
                push(rear.id, aim[0], send)

    # ── Phase 9: Total war (last 65 turns) ────────────────────────
    if world.is_total_war and world.enemy_planets and opt_ok():
        primary = ([p for p in world.enemy_planets if p.owner==world._weakest]
                   if world._weakest else world.enemy_planets)
        for src in world.my_planets:
            if expired(): return finalize()
            left = atk_left(src.id)
            if left < 5: continue
            to_try = primary if primary else world.enemy_planets
            best_t = None; best_d = float("inf")
            for ep in to_try:
                d = p_dist(src, ep)
                if d < best_d:
                    at = world.plan_shot(src.id, ep.id, left)
                    if at: best_d, best_t = d, ep
            if best_t is None: continue
            aim = world.plan_shot(src.id, best_t.id, left)
            if aim is None: continue
            angle,turns,_,_ = aim
            if turns>=world.remaining: continue
            push(src.id, angle, left)

    return finalize()


def _execute_mission(m, world, planned, modes, policy, moves, spent, inv_left, atk_left, push):
    """Execute a single mission (factored out for readability + hoard mode reuse)."""
    target = world.by_id[m.target_id]

    if m.kind in ("single","snipe","rescue","recapture","reinforce","crash_exploit"):
        opt  = m.options[0]
        src  = world.by_id[opt.src_id]
        left = (min(inv_left(opt.src_id), int(src.ships*REINF_MAX_SRC_FRAC))
                if m.kind=="reinforce" else atk_left(opt.src_id))
        if left<=0: return
        d = p_dist(src, target)
        if m.kind=="reinforce":
            plan = settle_reinf(src,target,left,min(left,opt.send_cap),
                                world,planned,opt.anchor_turn,m.turns)
        elif m.kind=="rescue":
            plan = settle_plan(src,target,left,min(left,opt.send_cap),world,planned,modes,policy,
                               mission="rescue",eval_fn=lambda _,f=m.turns:f,anchor=opt.anchor_turn)
        elif m.kind=="snipe":
            plan = settle_plan(src,target,left,min(left,opt.send_cap),world,planned,modes,policy,
                               mission="snipe",eval_fn=lambda t,ee=opt.anchor_turn:max(t,ee),
                               anchor=opt.anchor_turn)
        elif m.kind=="crash_exploit":
            plan = settle_plan(src,target,left,min(left,opt.send_cap),world,planned,modes,policy,
                               mission="crash_exploit",
                               eval_fn=lambda t,da=opt.anchor_turn:max(t,da),
                               anchor=opt.anchor_turn, anchor_tol=CRASH_ETA_WIN)
        else:
            plan = settle_plan(src,target,left,min(left,opt.send_cap),world,planned,modes,policy,
                               mission="capture", distance=d)
        if plan is None: return
        angle,turns,_,need,send = plan
        if send<need or need>left: return
        if m.kind in ("capture","single") and left>need:
            ts = speed_optimal_send(need, left, d, target.production)
            if ts >= need: send = ts
        sent = push(opt.src_id, angle, send)
        if sent<need: return
        planned[target.id].append((turns, world.player, int(sent)))
        return

    # Swarm
    lims = [min(atk_left(opt.src_id), opt.send_cap) for opt in m.options]
    if min(lims)<=0: return
    need = world.min_ships_to_own_at(target.id, m.turns, world.player,
                                     planned=planned, upper=sum(lims))
    if need<=0 or sum(lims)<need: return
    ordered = sorted(zip(m.options,lims), key=lambda x:(x[0].turns,-x[1],x[0].src_id))
    remaining=need; sends_map={}
    for idx,(opt,lim) in enumerate(ordered):
        rem_other = sum(l for _,l in ordered[idx+1:])
        s = min(lim, max(0, remaining-rem_other))
        sends_map[opt.src_id]=s; remaining-=s
    if remaining>0: return
    reaimed=[]
    for opt,_ in ordered:
        s = sends_map.get(opt.src_id,0)
        if s<=0: continue
        aim = world.plan_shot(opt.src_id, target.id, s)
        if aim is None: reaimed=[]; break
        reaimed.append((opt.src_id, aim[0], aim[1], s))
    if not reaimed: return
    ts_only=[x[2] for x in reaimed]
    tol = HOSTILE_SWARM_TOL if target.owner not in (-1,world.player) else MULTI_ETA_TOL
    if max(ts_only)-min(ts_only)>tol: return
    jt = max(ts_only)
    oo,_ = world.proj_state(target.id, jt, planned=planned,
                             extra=[(t,world.player,s) for _,_,t,s in reaimed])
    if oo!=world.player: return
    committed=[]
    for sid,angle,turns,s in reaimed:
        a=push(sid,angle,s)
        if a>0: committed.append((turns,world.player,int(a)))
    if sum(x[2] for x in committed)<need: return
    planned[target.id].extend(committed)

# ════════════════════════════════════════════════════════
# § 12  AGENT ENTRY POINT
# ════════════════════════════════════════════════════════

_step = 0

def _read(obs, key, default=None):
    if isinstance(obs, dict): return obs.get(key, default)
    return getattr(obs, key, default)

def build_world(obs, inferred_step=None):
    player    = _read(obs,"player",0)
    obs_step  = _read(obs,"step",0) or 0
    step      = max(obs_step, inferred_step or 0)
    planets   = [Planet(*p) for p in (_read(obs,"planets",[])  or [])]
    fleets    = [Fleet(*f)  for f in (_read(obs,"fleets",[])   or [])]
    ang_vel   = _read(obs,"angular_velocity",0.0) or 0.0
    init_raw  = _read(obs,"initial_planets",[]) or []
    comets    = _read(obs,"comets",[]) or []
    comet_ids = set(_read(obs,"comet_planet_ids",[]) or [])
    init_ps   = [Planet(*p) for p in init_raw]
    init_by_id= {p.id: p for p in init_ps}
    return WorldModel(player, step, planets, fleets, init_by_id, ang_vel, comets, comet_ids)

def agent(obs, config=None):
    global _step
    _step       += 1
    t0          = time.perf_counter()
    world       = build_world(obs, inferred_step=_step-1)
    if not world.my_planets: return []
    act_timeout = _read(config,"actTimeout",1.0) if config else 1.0
    budget      = min(SOFT_DEADLINE, max(0.55, act_timeout * 0.82))
    return plan_moves(world, deadline=t0+budget)

__all__ = ["agent", "build_world"]