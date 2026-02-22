"""
TwistedChess WebSocket server for Render deployment.
Run: uvicorn server:app --host 0.0.0.0 --port $PORT
"""
import asyncio, os
from contextlib import asynccontextmanager
SERVER_URL = os.environ.get("TWISTEDCHESS_SERVER", "wss://twistedchess.onrender.com/ws")

import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "websockets"])
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

rooms: dict[str, list[WebSocket]] = {}
_rooms_lock = asyncio.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for room in rooms.values():
        for ws in room:
            try:
                await ws.close()
            except Exception:
                pass


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/", methods=["GET", "HEAD"])

@app.get("/")
def health():
    """Health check for Render."""
    return {"status": "ok", "service": "twistedchess"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    code = ""
    player_index = -1

    try:
        # First message: room code
        raw = await websocket.receive_text()
        code = raw.strip()
        if not code:
            await websocket.close(code=1008)
            return

        async with _rooms_lock:
            if code not in rooms:
                rooms[code] = [websocket]
                player_index = 0
                await websocket.send_text("0")
                print(f"[{code}] created — waiting for second player")
            else:
                rooms[code].append(websocket)
                player_index = 1
                await websocket.send_text("1")
                print(f"[{code}] full — game on!")

        # Relay messages to the other player
        while True:
            data = await websocket.receive_text()
            async with _rooms_lock:
                room = rooms.get(code, [])
            if len(room) == 2:
                other = room[1 - player_index]
                try:
                    await other.send_text(data)
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        async with _rooms_lock:
            if code in rooms:
                try:
                    rooms[code].remove(websocket)
                except ValueError:
                    pass
                if not rooms[code]:
                    del rooms[code]
        try:
            await websocket.close()
        except Exception:
            pass
        print(f"Player {player_index} left room {code}")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 5555))
    uvicorn.run(app, host="0.0.0.0", port=port)
