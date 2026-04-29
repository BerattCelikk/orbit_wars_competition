import math
import time

# --- Constants ---
CENTER = (50.0, 50.0)
SUN_RADIUS = 10.1
MAX_SPEED = 6.0
BOARD_SIZE = 100.0
TOTAL_STEPS = 500

def get_dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)

def get_fleet_speed(ships):
    if ships <= 1: return 1.0
    clamped = max(1.0, min(1000.0, float(ships)))
    return 1.0 + (MAX_SPEED - 1.0) * ((math.log(clamped) / math.log(1000.0)) ** 1.5)

def path_hits_sun(x1, y1, x2, y2, safety=1.5): # Safety artırıldı, gemiler yanmayacak
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

class Planet:
    def __init__(self, data):
        self.id, self.owner, self.x, self.y, self.radius, self.ships, self.production = data
        self.incoming_allied = 0
        self.incoming_enemy = 0

def predict_pos(p, t, w, is_comet, comets_data):
    if is_comet:
        for g in comets_data:
            if p.id in g['planet_ids']:
                path = g['paths'][g['planet_ids'].index(p.id)]
                idx = g['path_index'] + int(t)
                if 0 <= idx < len(path): return path[idx]
                return None
        return p.x, p.y
    
    d_sun = get_dist(p.x, p.y, CENTER[0], CENTER[1])
    if d_sun + p.radius >= 50.0 or w == 0: return p.x, p.y
    angle = math.atan2(p.y - CENTER[1], p.x - CENTER[0]) + (w * t)
    return CENTER[0] + d_sun * math.cos(angle), CENTER[1] + d_sun * math.sin(angle)

def agent(obs):
    start_time = time.time()
    player = obs['player']
    step = obs['step']
    w = obs['angular_velocity']
    planets = [Planet(p) for p in obs['planets']]
    comet_ids = set(obs.get('comet_planet_ids', []))
    comets_data = obs.get('comets', [])
    
    p_map = {p.id: p for p in planets}
    
    # 1. Arrival Ledger & Threat Mapping
    for f_id, f_owner, f_x, f_y, f_angle, f_from, f_ships in obs['fleets']:
        dx, dy = math.cos(f_angle), math.sin(f_angle)
        best_t, target = 1e9, None
        for p in planets:
            px, py = p.x - f_x, p.y - f_y
            proj = px * dx + py * dy
            if proj > 0:
                perp = abs(px * dy - py * dx)
                if perp < p.radius + 1.5:
                    t_arr = proj / get_fleet_speed(f_ships)
                    if t_arr < best_t:
                        best_t, target = t_arr, p
        if target:
            if f_owner == player: target.incoming_allied += f_ships
            else: target.incoming_enemy += f_ships

    my_planets = [p for p in planets if p.owner == player]
    enemy_planets = [p for p in planets if p.owner != player and p.owner != -1]
    neutral_planets = [p for p in planets if p.owner == -1]
    
    actions = []
    time_left_global = TOTAL_STEPS - step
    
    # 2. Strategic Loop
    for src in sorted(my_planets, key=lambda x: x.production, reverse=True):
        
        # Dinamik Savunma: Arka cepheler gemi tutmasın, aksiyona aksın
        dist_to_closest_enemy = min([get_dist(src.x, src.y, e.x, e.y) for e in enemy_planets] + [999.0])
        buffer_multiplier = 1.0 if dist_to_closest_enemy > 40 else 3.0
        
        reserve = src.production * buffer_multiplier + max(0, src.incoming_enemy - src.incoming_allied)
        available = max(0, src.ships - max(3, reserve))
        
        if available < 1: continue

        best_score = -1e9
        best_target_move = None

        # Potential Targets
        for tgt in (neutral_planets + enemy_planets):
            tx, ty = tgt.x, tgt.y
            speed = get_fleet_speed(available)
            eta = get_dist(src.x, src.y, tx, ty) / speed
            
            # Mükemmel İsabet İçin 5 İterasyon
            valid_path = True
            for _ in range(5):
                pos = predict_pos(tgt, eta, w, tgt.id in comet_ids, comets_data)
                if pos is None: 
                    valid_path = False
                    break
                tx, ty = pos
                eta = get_dist(src.x, src.y, tx, ty) / speed
            
            if not valid_path or (step + eta) >= TOTAL_STEPS: continue
            if path_hits_sun(src.x, src.y, tx, ty, safety=1.5): continue

            # İhtiyaç Hesabı
            future_defense = tgt.ships + (tgt.production * eta if tgt.owner != -1 else 0)
            needed = int(future_defense + tgt.incoming_enemy - tgt.incoming_allied) + 2
            
            if needed > 0 and available >= needed:
                time_left = TOTAL_STEPS - (step + eta)
                
                # Oyun Sonu Modu (Endgame)
                if time_left_global < 60:
                    score = (tgt.ships * 15) / (needed * (eta + 1))
                else:
                    # Uzak mesafelere gitmeyi hafifçe cezalandır (eta ** 1.2)
                    score = (tgt.production * 15 * time_left) / (needed * (eta ** 1.2) + 1)
                    if tgt.owner == -1: score *= 1.5 # Tarafsızları almayı daha da teşvik et
                    elif tgt.id in comet_ids: score *= 0.6 # Kuyruklu yıldızlar kaybolduğu için risklidir

                if score > best_score:
                    best_score = score
                    best_target_move = (tx, ty, needed, tgt.id)

        # 3. Decision Execution
        if best_target_move:
            tx, ty, amt, tid = best_target_move
            angle = math.atan2(ty - src.y, tx - src.x)
            
            # Hızlandırma Bonusu: Eğer bolca gemimiz varsa, ihtiyacımız olanın %10 fazlasını yolla ki filo daha hızlı uçsun
            send_amt = amt
            if available > amt * 1.5 and available > 30:
                send_amt = min(available, int(amt * 1.1))
                
            actions.append([int(src.id), float(angle), int(send_amt)])
            src.ships -= send_amt
            p_map[tid].incoming_allied += send_amt # Overkill (Aşırı Yığılma) Koruması
        
        # 4. Logistics (Rear Funneling)
        elif available > 25 and enemy_planets:
            frontlines = sorted(my_planets, key=lambda p: min([get_dist(p.x, p.y, e.x, e.y) for e in enemy_planets]))
            if frontlines:
                frontline = frontlines[0]
                if frontline.id != src.id:
                    angle = math.atan2(frontline.y - src.y, frontline.x - src.x)
                    if not path_hits_sun(src.x, src.y, frontline.x, frontline.y, safety=1.5):
                        actions.append([int(src.id), float(angle), int(available)])
                        src.ships -= available

        # Kaggle Timeout Koruması
        if (time.time() - start_time) > 0.85: break

    return actions