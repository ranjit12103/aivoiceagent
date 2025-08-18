# main.py — Day 17: WebSocket streaming to AssemblyAI Realtime STT
import os
import json
import threading
import queue
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dotenv import load_dotenv
import assemblyai as aai  # pip install assemblyai

load_dotenv()

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
if not ASSEMBLYAI_API_KEY:
    print("⚠ ASSEMBLYAI_API_KEY missing in environment!")

# ---------- FastAPI setup ----------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------- Realtime STT pipeline ----------
class AAIRealtimeBridge:
    """
    Bridges incoming PCM16 mono 16kHz bytes to AssemblyAI RealtimeTranscriber.
    Uses a thread to keep the AAI streaming client running while the FastAPI
    WebSocket (async) receives audio bytes and pushes them into a Queue.
    """
    def __init__(self, sample_rate: int = 16000):
        if not ASSEMBLYAI_API_KEY:
            raise RuntimeError("ASSEMBLYAI_API_KEY not set")

        aai.settings.api_key = ASSEMBLYAI_API_KEY
        self.sample_rate = sample_rate
        self.audio_q: queue.Queue[bytes] = queue.Queue()
        self.transcriber: Optional[aai.RealtimeTranscriber] = None
        self.thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # Will be set by FastAPI handler to push transcripts back to client
        self.ws_send_func = None  # callable that takes str message

    def start(self):
        def on_open(session):
            print("✅ AAI Realtime session opened:", session)

        def on_data(transcript: aai.RealtimeTranscript):
            # transcript can be PartialTranscript or FinalTranscript
            payload = {
                "type": "transcript",
                "final": transcript.type == "FinalTranscript",
                "text": transcript.text or "",
            }
            # echo to console
            tag = "FINAL" if payload["final"] else "PARTIAL"
            print(f"[{tag}] {payload['text']}")
            # forward to client if available
            if self.ws_send_func:
                try:
                    self.ws_send_func(json.dumps(payload))
                except Exception as e:
                    print("WS send error:", e)

        def on_error(err: aai.RealtimeError):
            print("❌ AAI error:", err)
            if self.ws_send_func:
                try:
                    self.ws_send_func(json.dumps({
                        "type": "error",
                        "message": str(err),
                    }))
                except Exception as e:
                    print("WS send error:", e)

        def on_close():
            print("👋 AAI Realtime session closed")

        def worker():
            # Create realtime transcriber
            self.transcriber = aai.RealtimeTranscriber(
                sample_rate=self.sample_rate,
                on_open=on_open,
                on_data=on_data,
                on_error=on_error,
                on_close=on_close,
            )

            # Start the session
            with self.transcriber:
                self.transcriber.connect()

                # Pump audio frames from the queue to AAI until stop
                while not self._stop.is_set():
                    try:
                        chunk = self.audio_q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if chunk is None:
                        break
                    # IMPORTANT: send raw PCM16 mono bytes at 16kHz
                    self.transcriber.stream(chunk)

                # Finalize/close
                try:
                    self.transcriber.close()
                except Exception:
                    pass

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()

    def send_audio(self, pcm_bytes: bytes):
        if not self._stop.is_set():
            self.audio_q.put(pcm_bytes)

    def stop(self):
        self._stop.set()
        # Sentinel to break queue
        self.audio_q.put(None)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)


@app.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket):
    """
    Client connects and streams PCM16 mono 16kHz audio frames as binary messages.
    We forward frames to AssemblyAI Realtime and return partial/final transcripts
    back to the client as text JSON messages.
    """
    await websocket.accept()
    print("🌐 Client connected to /ws/transcribe")

    # Create the bridge + start AAI streaming
    bridge = AAIRealtimeBridge(sample_rate=16000)

    # attach function to send transcripts back to this websocket
    def ws_send(text: str):
        # Schedule send in a thread-safe way via anyio (FastAPI handles sync OK)
        try:
            # Note: send_text can be awaited; here we are in a different thread
            # but FastAPI allows calling send_text from threads; if not, we could
            # use starlette.concurrency.run_until_first_complete patterns.
            import asyncio
            asyncio.run(websocket.send_text(text))
        except RuntimeError:
            # If already in an event loop, dispatch a task
            import asyncio
            loop = asyncio.get_event_loop()
            loop.create_task(websocket.send_text(text))
        except Exception as e:
            print("send_text error:", e)

    bridge.ws_send_func = ws_send
    bridge.start()

    try:
        while True:
            # Expect binary frames of PCM16 mono @16kHz
            message = await websocket.receive()
            if "bytes" in message and message["bytes"] is not None:
                bridge.send_audio(message["bytes"])
            elif "text" in message and message["text"] is not None:
                # allow client to send control messages if needed
                txt = message["text"]
                if txt == "__close__":
                    break
            else:
                # ignore pings/empty
                pass
    except WebSocketDisconnect:
        print("⚠ Client disconnected from /ws/transcribe")
    finally:
        bridge.stop()
        try:
            await websocket.close()
        except Exception:
            pass
        print("🔌 WebSocket closed")
