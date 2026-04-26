#!/usr/bin/env python3
"""
SUBWAY RUN MULTIPLAYER SERVER
Starten: python server.py
Railway: automatisch
"""
import asyncio, json, os, random, string
import websockets
from websockets.server import serve

# Rooms: {code: {players: {id: ws}, state: {id: {...}}}}
rooms = {}

def make_code():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

def make_room():
    return {"players": {}, "state": {}, "started": False, "countdown": False}

async def broadcast(room_code, msg, exclude=None):
    room = rooms.get(room_code)
    if not room: return
    dead = []
    for pid, ws in room["players"].items():
        if pid == exclude: continue
        try:
            await ws.send(json.dumps(msg))
        except:
            dead.append(pid)
    for pid in dead:
        room["players"].pop(pid, None)
        room["state"].pop(pid, None)

async def handler(ws):
    player_id = None
    room_code = None
    try:
        async for raw in ws:
            msg = json.loads(raw)
            t = msg.get("type")

            if t == "create":
                # Create new room
                code = make_code()
                while code in rooms:
                    code = make_code()
                rooms[code] = make_room()
                player_id = "P1"
                room_code = code
                rooms[code]["players"][player_id] = ws
                rooms[code]["state"][player_id] = {"score": 0, "dead": False, "lane": 1, "z": 0}
                await ws.send(json.dumps({"type": "created", "code": code, "id": player_id}))

            elif t == "join":
                code = msg.get("code", "").upper().strip()
                if code not in rooms:
                    await ws.send(json.dumps({"type": "error", "msg": "Raum nicht gefunden!"}))
                    continue
                room = rooms[code]
                if len(room["players"]) >= 2:
                    await ws.send(json.dumps({"type": "error", "msg": "Raum ist voll!"}))
                    continue
                player_id = "P2"
                room_code = code
                room["players"][player_id] = ws
                room["state"][player_id] = {"score": 0, "dead": False, "lane": 1, "z": 0}
                await ws.send(json.dumps({"type": "joined", "code": code, "id": player_id}))
                # Tell P1 that P2 joined
                await broadcast(code, {"type": "opponent_joined", "id": player_id}, exclude=player_id)
                # Start countdown
                room["countdown"] = True
                for i in [3, 2, 1]:
                    await asyncio.sleep(1)
                    await broadcast(code, {"type": "countdown", "n": i})
                await asyncio.sleep(1)
                await broadcast(code, {"type": "start"})
                room["started"] = True

            elif t == "update" and room_code and player_id:
                # Player sends their state
                room = rooms.get(room_code)
                if not room: continue
                room["state"][player_id] = {
                    "score": msg.get("score", 0),
                    "dead": msg.get("dead", False),
                    "lane": msg.get("lane", 1),
                    "z": msg.get("z", 0),
                }
                # Send opponent state to this player
                opp_id = "P2" if player_id == "P1" else "P1"
                opp_state = room["state"].get(opp_id, {})
                await ws.send(json.dumps({"type": "opponent", **opp_state}))

                # Check if both dead → game over
                all_dead = all(s.get("dead") for s in room["state"].values() if s)
                if all_dead and len(room["state"]) == 2:
                    scores = {pid: s["score"] for pid, s in room["state"].items()}
                    winner = max(scores, key=scores.get)
                    await broadcast(code, {"type": "game_over", "scores": scores, "winner": winner})

            elif t == "ping":
                await ws.send(json.dumps({"type": "pong"}))

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if room_code and player_id:
            room = rooms.get(room_code)
            if room:
                room["players"].pop(player_id, None)
                room["state"].pop(player_id, None)
                if not room["players"]:
                    rooms.pop(room_code, None)
                else:
                    await broadcast(room_code, {"type": "opponent_left"})

async def main():
    port = int(os.environ.get("PORT", 8765))
    host = "0.0.0.0"
    print(f"Server läuft auf {host}:{port}")
    async with serve(handler, host, port):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
