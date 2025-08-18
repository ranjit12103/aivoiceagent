// static/script.js — Day 17 client: capture mic, downsample to 16kHz PCM16 mono, stream over WS

let ws = null;
let audioContext = null;
let processor = null;
let sourceNode = null;
let mediaStream = null;

const recordBtn = document.getElementById("recordBtn");
const statusDiv = document.getElementById("status");
const partialDiv = document.getElementById("partial");
const finalDiv = document.getElementById("final");

let isRecording = false;

// Utility: convert Float32 -> Int16 PCM
function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

// Utility: downsample buffer from srcRate -> 16kHz (mono)
function downsampleBuffer(buffer, srcSampleRate, outSampleRate = 16000) {
  if (outSampleRate === srcSampleRate) {
    return buffer;
  }
  const sampleRateRatio = srcSampleRate / outSampleRate;
  const newLength = Math.round(buffer.length / sampleRateRatio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
    // simple averaging to reduce high-frequency aliasing
    let accum = 0, count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }
    result[offsetResult] = accum / (count || 1);
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

async function startStreaming() {
  // 1) Open WS to server
  ws = new WebSocket(`ws://${window.location.host}/ws/transcribe`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    statusDiv.textContent = "Connected. Start speaking…";
  };

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.type === "transcript") {
        if (data.final) {
          // append final line
          const line = data.text.trim();
          if (line) {
            finalDiv.textContent += (finalDiv.textContent ? "\n" : "") + line;
          }
          partialDiv.textContent = "";
        } else {
          partialDiv.textContent = data.text;
        }
      } else if (data.type === "error") {
        statusDiv.textContent = `AssemblyAI Error: ${data.message}`;
      }
    } catch {
      // non-JSON messages ignored
    }
  };

  ws.onclose = () => {
    statusDiv.textContent = "Disconnected.";
  };

  // 2) Capture mic with Web Audio API
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
  sourceNode = audioContext.createMediaStreamSource(mediaStream);

  // ScriptProcessor is deprecated but simplest cross-browser approach
  const bufferSize = 4096;
  processor = audioContext.createScriptProcessor(bufferSize, 1, 1);

  processor.onaudioprocess = (e) => {
    // capture mono channel 0
    const input = e.inputBuffer.getChannelData(0);
    // downsample to 16kHz
    const downsampled = downsampleBuffer(input, audioContext.sampleRate, 16000);
    // float -> int16 PCM
    const pcm16 = floatTo16BitPCM(downsampled);
    // send as ArrayBuffer
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(pcm16.buffer);
    }
  };

  sourceNode.connect(processor);
  processor.connect(audioContext.destination); // required in some browsers even if we don't want to hear it
}

function stopStreaming() {
  // Stop audio graph
  try { processor && processor.disconnect(); } catch {}
  try { sourceNode && sourceNode.disconnect(); } catch {}
  try { audioContext && audioContext.close(); } catch {}
  try { mediaStream && mediaStream.getTracks().forEach(t => t.stop()); } catch {}

  // Close websocket
  try { ws && ws.readyState === WebSocket.OPEN && ws.send("__close__"); } catch {}
  try { ws && ws.close(); } catch {}

  ws = null;
  audioContext = null;
  processor = null;
  sourceNode = null;
  mediaStream = null;
}

recordBtn.addEventListener("click", async () => {
  if (!isRecording) {
    try {
      isRecording = true;
      recordBtn.classList.add("recording");
      recordBtn.textContent = "⏹️";
      statusDiv.textContent = "Connecting…";
      partialDiv.textContent = "";
      // don't clear final; we append
      await startStreaming();
    } catch (e) {
      isRecording = false;
      recordBtn.classList.remove("recording");
      recordBtn.textContent = "🎙️";
      statusDiv.textContent = `Error: ${e?.message || e}`;
    }
  } else {
    isRecording = false;
    recordBtn.classList.remove("recording");
    recordBtn.textContent = "🎙️";
    statusDiv.textContent = "Stopping…";
    stopStreaming();
  }
});
