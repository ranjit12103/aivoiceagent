# main.py - Day 15: WebSocket Echo Server

from fastapi import FastAPI, Form, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import requests
import os
import io
import assemblyai as aai
import google.generativeai as genai

# Load environment variables
load_dotenv()

app = FastAPI()

# Static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

# API Keys
MURF_API_KEY = os.getenv("MURF_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure APIs
if ASSEMBLYAI_API_KEY:
    aai.settings.api_key = ASSEMBLYAI_API_KEY
else:
    print("⚠ Missing AssemblyAI API Key")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("⚠ Missing Gemini API Key")

os.makedirs("uploads", exist_ok=True)

MURF_API_URL = "https://api.murf.ai/v1/speech/generate"


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# WebSocket Echo (Day 15 Task)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📩 Received: {data}")
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        print("⚠ Client disconnected")


@app.post("/agent/chat/{session_id}")
async def agent_chat(
    session_id: str,
    audio_file: UploadFile = File(...),
    voiceId: str = Form("en-US-natalie")
):
    """STT → LLM → TTS pipeline"""
    if not (MURF_API_KEY and ASSEMBLYAI_API_KEY and GEMINI_API_KEY):
        return JSONResponse(status_code=500, content={"error": "Missing API keys."})

    try:
        # Step 1: Read audio
        audio_bytes = await audio_file.read()

        # Step 2: STT
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(io.BytesIO(audio_bytes))
        if transcript.status == aai.TranscriptStatus.error:
            return JSONResponse(status_code=500, content={"error": transcript.error})
        user_text = transcript.text.strip()

        # Step 3: LLM
        model = genai.GenerativeModel("gemini-1.5-flash")
        gemini_response = model.generate_content(user_text)
        llm_text = gemini_response.text.strip()

        # Step 4: TTS (Murf)
        llm_text = llm_text[:3000]
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": MURF_API_KEY
        }
        payload = {"text": llm_text, "voiceId": voiceId, "format": "MP3", "sampleRate": 24000}
        resp = requests.post(MURF_API_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        audio_url = data.get("audioFile") or data.get("audio_url") or data.get("audioUrl")

        if not audio_url:
            return JSONResponse(status_code=500, content={"error": "TTS failed", "details": data})

        return {"llm_response": llm_text, "audio_url": audio_url}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Server error: {str(e)}"})
