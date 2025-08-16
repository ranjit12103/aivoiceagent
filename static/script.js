document.addEventListener("DOMContentLoaded", () => {
  let recorder, chunks = [];
  const recordBtn = document.getElementById("recordBtn");
  const statusDiv = document.getElementById("status");
  const responseDiv = document.getElementById("response");
  const audioPlayer = document.getElementById("audioPlayer");

  let recording = false;

  recordBtn.addEventListener("click", async () => {
    if (!recording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(stream);
        chunks = [];
        recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
        recorder.onstop = sendAudio;

        recorder.start();
        recording = true;
        recordBtn.classList.add("recording");
        recordBtn.textContent = "⏹️";
        statusDiv.textContent = "Recording... Tap to stop.";
      } catch {
        alert("Microphone access denied.");
      }
    } else {
      recorder.stop();
      recording = false;
      recordBtn.classList.remove("recording");
      recordBtn.textContent = "🎙️";
      statusDiv.textContent = "Processing...";
    }
  });

  async function sendAudio() {
    const blob = new Blob(chunks, { type: "audio/webm" });
    const form = new FormData();
    form.append("audio_file", blob, "input.webm");
    form.append("voiceId", "en-US-natalie");

    try {
      const res = await fetch("/agent/chat/demo-session", {
        method: "POST",
        body: form
      });

      const data = await res.json();
      if (res.ok) {
        responseDiv.innerHTML = `<b>AI:</b> ${data.llm_response}`;
        audioPlayer.src = data.audio_url;
        audioPlayer.hidden = false;
        audioPlayer.play();
        statusDiv.textContent = "";
      } else {
        statusDiv.textContent = `Error: ${data.error || 'Unknown error'}`;
      }
    } catch (err) {
      statusDiv.textContent = "Network error.";
    }
  }
});
