import math
import time

# --- OYUN SABİTLERİ ---
CENTER = (50.0, 50.0)      
SUN_RADIUS = 10.1          
MAX_SPEED = 6.0            
TOTAL_STEPS = 500          

# --- HIZLI MATEMATİK & FİZİK ---
def get_dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)

def get_fleet_speed(ships):
    if ships <= 1: return 1.0
    clamped = max(1.0, min(1000.0, float(ships)))
    return 1.0 + (MAX_SPEED - 1.0) * ((math.log(clamped) / math.log(1000.0)) ** 1.5)

def path_hits_sun(x1, y1, x2, y2, safety=1.65):
    r = SUN_RADIUS + safety
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - CENTER[0], y1 - CENTER[1]
    
    a = dx*dx + dy*dy
    if a < 1e-9: return get_dist(x1, y1, CENTER[0], CENTER[1]) < r
    
    b = 2 * (fx*dx + fy*dy)
    c = fx*fx + fy*fy - r*r
    disc = b*b - 4*a*c
    
    if disc < 0: return False
    disc = math.sqrt(disc)
    t1, t2 = (-b - disc)/(2*a), (-b + disc)/(2*a)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1)

def predict_pos(p_data, t, w, is_comet, comets_data):
    if is_comet:
        for g in comets_data:
            if p_data['id'] in g['planet_ids']:
                idx = g['planet_ids'].index(p_data['id'])
                path = g['paths'][idx]
                target_idx = g['path_index'] + int(t)
                if 0 <= target_idx < len(path): return path[target_idx]
                return None 
        return p_data['x'], p_data['y']
    
    d_sun = get_dist(p_data['x'], p_data['y'], CENTER[0], CENTER[1])
    if d_sun + p_data['radius'] >= 50.0 or w == 0: 
        return p_data['x'], p_data['y'] 
    
    angle = math.atan2(p_data['y'] - CENTER[1], p_data['x'] - CENTER[0]) + (w * t)
    return CENTER[0] + d_sun * math.cos(angle), CENTER[1] + d_sun * math.sin(angle)

# --- ZAMAN ÇİZELGESİ SİMÜLATÖRÜ ---
class PlanetNode:
    def __init__(self, data):
        self.id, self.owner, self.x, self.y, self.radius, self.ships, self.production = data
        self.raw_data = {'id': self.id, 'x': self.x, 'y': self.y, 'radius': self.radius}
        self.arrivals = [] 

    def add_arrival(self, eta, owner, ships):
        self.arrivals.append((eta, owner, ships))

    def get_future_state(self, target_eta):
        curr_owner, curr_ships = self.owner, self.ships
        self.arrivals.sort(key=lambda x: x[0])
        last_t = 0
        for arr_t, arr_owner, arr_ships in self.arrivals:
            if arr_t > target_eta: break
            dt = arr_t - last_t
            if curr_owner != -1: curr_ships += self.production * dt
            if arr_owner == curr_owner: curr_ships += arr_ships
            else:
                if arr_ships > curr_ships:
                    curr_owner, curr_ships = arr_owner, arr_ships - curr_ships
                else: curr_ships -= arr_ships
            last_t = arr_t
        dt = target_eta - last_t
        if curr_owner != -1: curr_ships += self.production * dt
        return curr_owner, curr_ships

    def get_required_defense(self, max_turns, player):
        if self.owner != player: return 0
        min_surplus, curr_owner, curr_ships = self.ships, self.owner, self.ships
        last_t = 0
        self.arrivals.sort(key=lambda x: x[0])
        for arr_t, arr_owner, arr_ships in self.arrivals:
            if arr_t > max_turns: break
            dt = arr_t - last_t
            curr_ships += self.production * dt
            if arr_owner == curr_owner: curr_ships += arr_ships
            else:
                curr_ships -= arr_ships
                if curr_ships < 0: curr_owner, curr_ships = arr_owner, -curr_ships
            min_surplus = min(min_surplus, curr_ships if curr_owner == player else -curr_ships)
            last_t = arr_t
        return max(0, -min_surplus)

# --- ANA YAPAY ZEKA (APEX PREDATOR) ---
def agent(obs):
    start_time = time.time()
    player = obs['player']
    step = obs['step']
    w = obs['angular_velocity']
    time_left = TOTAL_STEPS - step
    comet_ids = set(obs.get('comet_planet_ids', []))
    comets_data = obs.get('comets', [])
    planets = {p[0]: PlanetNode(p) for p in obs['planets']}
    
    active_players = set([p.owner for p in planets.values() if p.owner != -1])
    is_ffa = len(active_players) > 2
    
    # 1. GLOBAL RADAR: Uçan tüm filoları işle
    for f in obs['fleets']:
        f_owner, f_x, f_y, f_angle, f_ships = f[1], f[2], f[3], f[4], f[6]
        dx, dy = math.cos(f_angle), math.sin(f_angle)
        best_t, target_id = 1e9, None
        for pid, p in planets.items():
            px, py = p.x - f_x, p.y - f_y
            proj = px * dx + py * dy
            if proj > 0:
                perp = abs(px * dy - py * dx)
                if perp < p.radius + 1.2:
                    t_arr = proj / get_fleet_speed(f_ships)
                    if t_arr < best_t: best_t, target_id = t_arr, pid
        if target_id is not None:
            planets[target_id].add_arrival(best_t, f_owner, f_ships)

    my_planets = [p for p in planets.values() if p.owner == player]
    enemy_planets = [p for p in planets.values() if p.owner not in [player, -1]]
    
    # 2. GHOST THREAT (Hayalet Tehdit) & GÜVENLİ HAVUZ
    available_pool = {}
    for src in my_planets:
        ghost_threat = 0
        closest_enemy_dist = 999.0
        for e in enemy_planets:
            dist = get_dist(src.x, src.y, e.x, e.y)
            if dist < closest_enemy_dist: closest_enemy_dist = dist
            eta_threat = dist / MAX_SPEED
            if eta_threat < 12: 
                potential_dmg = e.ships - (src.ships + src.production * eta_threat)
                if potential_dmg > ghost_threat: ghost_threat = int(potential_dmg * 0.4) 
                
        safe_turns = closest_enemy_dist / MAX_SPEED
        buffer = 0 if safe_turns > 12 else int(src.production * 1.5) + ghost_threat
        
        req_def = src.get_required_defense(time_left, player)
        avail = int(src.ships - (req_def + buffer))
        available_pool[src.id] = max(0, avail)

    actions = []
    candidate_moves = []
    all_targets = list(planets.values())
    
    # 3. KUANTUM HEDEF PUANLAMASI & S.O.S SAVUNMA
    for src in my_planets:
        if available_pool[src.id] <= 0: continue
        
        for tgt in all_targets:
            if src.id == tgt.id: continue
            
            is_comet = tgt.id in comet_ids
            speed = get_fleet_speed(available_pool[src.id])
            eta = get_dist(src.x, src.y, tgt.x, tgt.y) / speed
            
            valid_path, tx, ty = True, tgt.x, tgt.y
            for _ in range(4): 
                pos = predict_pos(tgt.raw_data, eta, w, is_comet, comets_data)
                if pos is None: 
                    valid_path = False; break
                tx, ty = pos
                eta = get_dist(src.x, src.y, tx, ty) / speed
                
            if not valid_path or (step + eta) >= TOTAL_STEPS or path_hits_sun(src.x, src.y, tx, ty):
                continue

            if is_comet:
                pos_after_capture = predict_pos(tgt.raw_data, eta + 12, w, True, comets_data)
                if pos_after_capture is None: continue 

            future_owner, future_ships = tgt.get_future_state(eta)
            
            if tgt.owner == player:
                if future_owner == player: continue 
                ships_needed = max(1, int(future_ships + 2))
                score = (tgt.production * 2000) / (ships_needed * eta) 
            else:
                if future_owner == player: continue 
                ships_needed = max(1, int(future_ships + 2))
                enemy_multiplier = 2.0 if is_ffa else 4.0
                
                if time_left < 70:
                    score = (tgt.ships * 20) / (ships_needed * (eta + 1))
                else:
                    net_prod = tgt.production * (time_left - eta)
                    if is_comet: net_prod *= 0.3 
                    multiplier = enemy_multiplier if tgt.owner != -1 else 1.8 
                    net_profit = (net_prod * multiplier) - ships_needed
                    score = net_profit / (eta ** 1.4) 

            if score > 0:
                candidate_moves.append({
                    'score': score, 'src_id': src.id, 'tgt_id': tgt.id, 
                    'base_req': ships_needed, 'tx': tx, 'ty': ty, 'eta': eta
                })

    candidate_moves.sort(key=lambda x: x['score'], reverse=True)

    # 4. DİNAMİK SİMÜLASYON ENJEKSİYONU (Swarm Attack)
    for move in candidate_moves:
        sid, tid, eta, tx, ty = move['src_id'], move['tgt_id'], move['eta'], move['tx'], move['ty']
        if available_pool[sid] <= 0: continue
        
        current_future_owner, current_future_ships = planets[tid].get_future_state(eta)
        if current_future_owner == player: continue 
            
        real_req = max(1, int(current_future_ships + 2))
        
        if available_pool[sid] >= real_req:
            angle = math.atan2(ty - planets[sid].y, tx - planets[sid].x)
            actions.append([int(sid), float(angle), int(real_req)])
            available_pool[sid] -= real_req
            planets[tid].add_arrival(eta, player, real_req) 
            
        if (time.time() - start_time) > 0.85: break

    # 5. AKILLI LOJİSTİK (Çoklu-Cephe Duvarı)
    if (time.time() - start_time) < 0.85:
        for src in my_planets:
            if available_pool[src.id] > 30 and enemy_planets:
                frontlines = sorted([p for p in my_planets if p.id != src.id], 
                                    key=lambda p: min([get_dist(p.x, p.y, e.x, e.y) for e in enemy_planets]))
                
                if frontlines:
                    targets = [(frontlines[0], 1.0)]
                    if len(frontlines) > 1:
                        targets = [(frontlines[0], 0.6), (frontlines[1], 0.4)]
                        
                    for f_planet, ratio in targets:
                        send_amount = int(available_pool[src.id] * ratio)
                        if send_amount < 5: continue
                        
                        angle = math.atan2(f_planet.y - src.y, f_planet.x - src.x)
                        if not path_hits_sun(src.x, src.y, f_planet.x, f_planet.y):
                            actions.append([int(src.id), float(angle), send_amount])
                            
            if (time.time() - start_time) > 0.90: break

    return actions