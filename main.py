# main.py - Day 16: Streaming Audio via WebSockets

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

app = FastAPI()

# Mount static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

# Ensure uploads folder exists
os.makedirs("uploads", exist_ok=True)


@app.get("/")
async def home(request: Request):
    """Serve index.html"""
    return templates.TemplateResponse("index.html", {"request": request})


# WebSocket endpoint for streaming audio
@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    file_path = "uploads/streamed_audio.webm"

    # Open file for writing binary chunks
    with open(file_path, "wb") as f:
        try:
            while True:
                # Receive binary audio data
                data = await websocket.receive_bytes()
                f.write(data)
                # Acknowledge receipt
                await websocket.send_text("✅ Chunk received")
        except WebSocketDisconnect:
            print(f"⚠ Client disconnected. Audio saved at: {file_path}")
