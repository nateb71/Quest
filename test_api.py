"""
Quest API Test Script
---------------------
Tests all backend endpoints from Step 1 (register) through Step 7 (logout).

How to run:
    1. Start the server in one terminal:  python app.py
    2. Run this script in another:        python test_api.py

Each [PASS] / [FAIL] line is one check against a backend endpoint.
The script stops and prints the failure details if something is broken.

NOTE: Step 6 (combat) calls the OpenAI API several times.
      It will be slower than the other steps and will use API credits.
"""

import time
import requests

BASE     = "http://127.0.0.1:5000"

ts          = str(int(time.time()))
P1_USERNAME = f"tester1_{ts}"
P2_USERNAME = f"tester2_{ts}"
PASSWORD    = "password123"


def check(label, condition, info=""):
    if condition:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}")
        if info:
            print(f"         Server said: {info}")
        print("\n  Test stopped. Fix the failure above before re-running.\n")
        raise SystemExit(1)


# ==================================================================
# Step 1 — Register two accounts
# ==================================================================
print("\n--- Step 1: Register ---")

r = requests.post(f"{BASE}/auth/register", json={
    "username": P1_USERNAME, "email": f"{P1_USERNAME}@test.com", "password": PASSWORD
})
check("Register player 1", r.status_code == 201, r.text)

r = requests.post(f"{BASE}/auth/register", json={
    "username": P2_USERNAME, "email": f"{P2_USERNAME}@test.com", "password": PASSWORD
})
check("Register player 2", r.status_code == 201, r.text)


# ==================================================================
# Step 2 — Login
# Each player needs their own session object to keep cookies separate.
# ==================================================================
print("\n--- Step 2: Login ---")

p1 = requests.Session()
p2 = requests.Session()

r = p1.post(f"{BASE}/auth/login", json={"username": P1_USERNAME, "password": PASSWORD})
check("Player 1 login", r.status_code == 200, r.text)

r = p2.post(f"{BASE}/auth/login", json={"username": P2_USERNAME, "password": PASSWORD})
check("Player 2 login", r.status_code == 200, r.text)

r = p1.post(f"{BASE}/auth/login", json={"username": P1_USERNAME, "password": "wrongpassword"})
check("Wrong password is rejected (401)", r.status_code == 401, r.text)


# ==================================================================
# Step 3 — Create a game session (Player 1 hosts)
# ==================================================================
print("\n--- Step 3: Create Session ---")

r = p1.post(f"{BASE}/session/create", json={"character_name": "Gareth", "role": "warrior"})
check("Player 1 creates session", r.status_code == 201, r.text)

session_id  = r.json()["session_id"]
invite_code = r.json()["invite_code"]
print(f"         session_id  = {session_id}")
print(f"         invite_code = {invite_code}")

r = p1.post(f"{BASE}/session/create", json={"character_name": "X", "role": "paladin"})
check("Invalid role is rejected (400)", r.status_code == 400, r.text)


# ==================================================================
# Step 4 — Join the session (Player 2 joins)
# When player 2 joins, the backend calls the AI to generate a unique
# adventure outline (title, boss, starting scene).
# ==================================================================
print("\n--- Step 4: Join Session (AI generates adventure outline) ---")

r = p2.post(f"{BASE}/session/join", json={
    "invite_code": "BADCODE", "character_name": "Lyra", "role": "mage"
})
check("Wrong invite code is rejected (404)", r.status_code == 404, r.text)

print("  Waiting for AI to generate adventure outline...")
r = p2.post(f"{BASE}/session/join", json={
    "invite_code": invite_code, "character_name": "Lyra", "role": "mage"
})
check("Player 2 joins with correct code", r.status_code == 200, r.text)
check("Session status becomes active", r.json().get("status") == "active", r.text)

r = p2.post(f"{BASE}/session/join", json={
    "invite_code": invite_code, "character_name": "Lyra", "role": "mage"
})
check("Joining twice is rejected (400)", r.status_code == 400, r.text)


# ==================================================================
# Step 5 — Check the starting game state
# ==================================================================
print("\n--- Step 5: Game State ---")

r = p1.get(f"{BASE}/session/{session_id}/state")
check("Can fetch game state", r.status_code == 200, r.text)

gs = r.json()["game_state"]
check("Both players appear in the state",
      "player_1" in gs["entities"] and "player_2" in gs["entities"])
check("Player 1 is a warrior",   gs["entities"]["player_1"]["role"] == "warrior")
check("Player 2 is a mage",      gs["entities"]["player_2"]["role"] == "mage")
check("Warrior starts at 30 HP", gs["entities"]["player_1"]["hp"] == 30,
      f"got {gs['entities']['player_1']['hp']}")
check("Mage starts at 18 HP",    gs["entities"]["player_2"]["hp"] == 18,
      f"got {gs['entities']['player_2']['hp']}")
check("Mage starts at 30 MP",    gs["entities"]["player_2"]["mp"] == 30,
      f"got {gs['entities']['player_2']['mp']}")
check("Mage max MP is 30",      gs["entities"]["player_2"]["max_mp"] == 30,
      f"got {gs['entities']['player_2']['max_mp']}")
check("Combat has not started yet", gs["in_combat"] == False)

adventure_title = gs["adventure"]["title"]
scene_seed      = gs["scene"]["description_seed"]
story_flags     = gs["adventure"]["story_flags"]
print(f"         Adventure title : {adventure_title}")
print(f"         Scene           : {scene_seed}")
check("AI generated a unique adventure title",
      adventure_title != "A New Adventure", f"got '{adventure_title}'")
check("All 3 chapter seeds stored",
      all(f"chapter_{n}_seed" in story_flags for n in [1, 2, 3]))
check("Opening narration generated",
      "opening_narration" in story_flags and len(story_flags["opening_narration"]) > 0)
print(f"         Opening narration: {story_flags.get('opening_narration', '')[:100]}")


# ==================================================================
# Step 6 — Combat
# The first action triggers enemy spawning via AI, then processes
# the attack. Subsequent turns continue until the enemy is dead.
# ==================================================================
print("\n--- Step 6: Combat ---")
print("  (Each action calls OpenAI — expect a few seconds per turn)")

# First action — also triggers enemy spawn and initiative roll on the backend.
# Initiative is random, so player_2 might go first. If player_1 is rejected
# with "Not the actor's turn", we read the initiative order from the response
# (it's included even on failure) and retry with whoever is actually first.
print("\n  Submitting first action... (AI spawning enemy + rolling initiative)")
r = p1.post(f"{BASE}/session/{session_id}/action", json={
    "actor_id":           "player_1",
    "action_description": "I attack the nearest enemy with my sword"
})
check("First action HTTP 200", r.status_code == 200, r.text)

if not r.json().get("valid"):
    gs_retry = r.json()["game_state"]
    order     = gs_retry.get("initiative_order", [])
    idx       = gs_retry.get("current_turn_index", 0)
    first_actor = order[idx % len(order)] if order else "player_2"
    print(f"  Player 1 is not first in initiative — {first_actor} goes first, retrying")
    sess = p2 if first_actor == "player_2" else p1
    action_text = "I cast a spell at the nearest enemy" if first_actor == "player_2" else "I attack the nearest enemy with my sword"
    r = sess.post(f"{BASE}/session/{session_id}/action", json={
        "actor_id":           first_actor,
        "action_description": action_text,
    })
    check("First action (correct player) HTTP 200", r.status_code == 200, r.text)

check("First action valid", r.json().get("valid") == True, r.json().get("message"))
print(f"  DM says: {r.json().get('message', '')[:120]}")

# Show what enemy was spawned and its current HP
enemies = {k: v for k, v in r.json()["game_state"]["entities"].items() if v["type"] == "enemy"}
for eid, ent in enemies.items():
    print(f"  Enemy spawned: {eid}  |  HP: {ent['hp']}/{ent['max_hp']}")

check("An enemy was spawned", len(enemies) > 0, "No enemy entity found in game state")
enemy_id = list(enemies.keys())[0]

# Keep taking turns until the session ends (all 3 chapters cleared)
actor_map = {"player_1": (p1, "I attack the enemy with my sword"),
             "player_2": (p2, "I cast a spell at the enemy")}

final = r.json()
for turn in range(2, 30):
    if final.get("session_over"):
        break

    gs       = final["game_state"]
    order    = gs.get("initiative_order", [])
    idx      = gs.get("current_turn_index", 0)
    actor_id = order[idx % len(order)] if order else None

    # actor_id is None between chapters (initiative_order is empty).
    # Default to player_1 to trigger the next chapter's enemy spawn.
    if actor_id not in actor_map:
        actor_id = "player_1"

    sess, action_text = actor_map[actor_id]
    chapter = gs["adventure"]["current_chapter"]
    print(f"\n  Turn {turn} (chapter {chapter}): {actor_id} — \"{action_text}\" (waiting for OpenAI...)")
    r = sess.post(f"{BASE}/session/{session_id}/action", json={
        "actor_id":           actor_id,
        "action_description": action_text,
    })
    check(f"Turn {turn} accepted", r.status_code == 200, r.text)

    # Each chapter re-rolls initiative, so the expected actor might not be first.
    # If rejected for that reason, read who is actually first and retry once.
    if not r.json().get("valid") and "Not the actor's turn" in r.json().get("message", ""):
        gs_retry  = r.json()["game_state"]
        new_order = gs_retry.get("initiative_order", [])
        new_idx   = gs_retry.get("current_turn_index", 0)
        retry_id  = new_order[new_idx % len(new_order)] if new_order else ("player_2" if actor_id == "player_1" else "player_1")
        if retry_id in actor_map:
            print(f"  Initiative re-rolled — {retry_id} goes first, retrying")
            sess, action_text = actor_map[retry_id]
            r = sess.post(f"{BASE}/session/{session_id}/action", json={
                "actor_id":           retry_id,
                "action_description": action_text,
            })
            check(f"Turn {turn} retry accepted", r.status_code == 200, r.text)

    check(f"Turn {turn} valid",    r.json().get("valid") == True, r.json().get("message"))
    print(f"  DM says: {r.json().get('message', '')[:120]}")

    current_enemies = {k: v for k, v in r.json()["game_state"]["entities"].items()
                       if v["type"] == "enemy" and v["hp"] > 0}
    for eid, ent in current_enemies.items():
        print(f"  {eid} HP: {ent['hp']}/{ent['max_hp']}")

    final = r.json()

check("Session ended after 3 chapters", final.get("session_over") == True)
check("Players won", final.get("winner") == "players", f"winner = {final.get('winner')!r}")


# ==================================================================
# Step 7 — Logout
# ==================================================================
print("\n--- Step 7: Logout ---")

r = p1.post(f"{BASE}/auth/logout")
check("Player 1 logged out", r.status_code == 200, r.text)

r = p1.get(f"{BASE}/session/{session_id}/state")
check("Requests after logout are rejected (401)", r.status_code == 401, r.text)


print("\n--- All checks passed ---\n")
