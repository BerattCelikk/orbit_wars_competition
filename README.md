# 🌌 Orbit Wars: Supreme Tactical AI Agents

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)
![Kaggle](https://img.shields.io/badge/Kaggle-Competition-20beff.svg?logo=kaggle&logoColor=white)
![AI/Bot](https://img.shields.io/badge/AI_Agent-Autonomous-success.svg)
![Status](https://img.shields.io/badge/Status-Completed-brightgreen.svg)

> High-performance autonomous AI agents developed for the Kaggle **Orbit Wars** simulation. This repository showcases the evolution of tactical bot development, culminating in an advanced 8-layer architecture featuring timeline simulation, orbital prediction, and dynamic game theory tactics.

---

## 📑 Table of Contents
- [About The Project](#-about-the-project)
- [Agent Evolution & Leaderboard](#-agent-evolution--leaderboard)
- [Core Technologies (The 8-Layer Architecture)](#-core-technologies-the-8-layer-architecture)
- [Repository Structure](#-repository-structure)
- [Getting Started](#-getting-started)
- [Author](#-author)

---

## 🎯 About The Project

**Orbit Wars** is a highly complex 2D real-time space strategy simulation. Players command fleets across a solar system to capture planets, manage production economies, and eliminate opponents in 1v1 or 4-player Free-For-All (FFA) environments.

The agents in this repository do not rely on simple heuristics. Instead, they utilize **mathematical optimization, forward-projection timeline simulations, and micro-logistics algorithms** to systematically outplay opponents.

---

## 🧬 Agent Evolution & Leaderboard

This repository tracks the evolutionary leap of the agents, from baseline greedy algorithms to supreme intelligence.

| Agent Name | Public Score | Key Strategic Innovation | Status |
| :--- | :---: | :--- | :---: |
| **Archangel v2** | `681.0` | ROI-based scoring, basic orbital prediction | 🟢 |
| **OMEGA v3** | `678.5` | Binary-search timeline simulation, 12 mission types | 🟢 |
| **OMEGA v5** | `644.7` | Planet Triage, Simultaneous Counter-Rush | 🟢 |
| **OMEGA v7 Supreme**| `Top Tier` | Ship Hoarding Mode, Cluster Bonus Synergy | 🟢 |
| **HYPERION** | `700+` | **Opening Blitz**, Flanking Multiplier, Total War routing | 🌟 |

---

## ⚙️ Core Technologies (The 8-Layer Architecture)

The pinnacle of this repository, **HYPERION**, operates on a ruthless 8-layer cognitive architecture:

1. **Physics & Routing:** Solves the moving-target problem via 7-iteration orbital convergence and uses trigonometric raycasting for *Solar Bypass* routing.
2. **World Model Simulation:** Runs a full turn-by-turn simulation (with $O(\log N)$ binary search) to calculate the exact minimum garrison required to survive future attacks.
3. **Dynamic Economic Modes:** Continuously tracks the production ratio against enemies to switch between 5 behavioral states (`SNOWBALL`, `EXPAND`, `BALANCED`, `AGGRO`, `PANIC`).
4. **Policy Builder:** Implements the *Opening Blitz* protocol, aggressively cutting reserves in the first 22 turns to leverage compound production.
5. **Scoring Engine:** A hyper-optimized mathematical formula utilizing 14 distinct multipliers, including a massive **×5.94** bonus for *Vulnerability Window* exploits.
6. **Mission Engine:** Capable of orchestrating 14 simultaneous mission types (Snipe, Swarm, Counter-Rush, Intercept, etc.).
7. **Executor (Hyper-Tsunami):** Exploits the game's logarithmic fleet speed curve. Deliberately over-sends ships when mathematically justified to gain free turns.
8. **Endgame State Machine:** Tracks the exact win/loss delta in the final 35 turns, deciding precisely when to enter *Death Ball (Defend)* or *All-In* modes.

---

## 📂 Repository Structure

The project is cleanly divided into pure, execution-ready agent scripts and detailed Jupyter Notebooks that break down the math and logic behind the code.

```text
📦 ORBIT_WARS_COMPETITION
├── 📂 agents                       # Raw, competition-ready Python scripts
│   ├── archangel_v2.py
│   ├── omega_v3.py
│   ├── omega_v5_supreme.py
│   ├── omega_v7_supreme.py
│   └── hyperion_supreme.py         # The final 700+ Elo agent
│
├── 📂 notebooks                    # Deep-dive educational breakdowns
│   ├── 01_apex_predator_strategy.ipynb
│   ├── 02_apex_predator_breakdown.ipynb
│   ├── 03_omega_domination_engine.ipynb
│   ├── 04_apex_predator_ffa.ipynb
│   ├── 05_omega_v3_breakdown.ipynb
│   ├── 06_omega_v5_supreme_domination.ipynb
│   ├── 07_omega_v7_supreme_breakdown.ipynb
│   └── 08_hyperion_supreme_breakdown.ipynb
│
└── 📄 README.md                    # Project documentation
