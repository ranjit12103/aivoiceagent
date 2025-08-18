document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const statusDiv = document.getElementById("status");
  const log = document.getElementById("log");

  let recording = false;
  let socket, recorder;

  recordBtn.addEventListener("click", async () => {
    if (!recording) {
      try {
        // Open WebSocket
        socket = new WebSocket(`ws://${window.location.host}/ws/stream`);
        socket.binaryType = "arraybuffer";

        socket.onopen = async () => {
          logMessage("✅ Connected to server");
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          recorder = new MediaRecorder(stream);

          recorder.ondataavailable = e => {
            if (e.data.size > 0 && socket.readyState === WebSocket.OPEN) {
              e.data.arrayBuffer().then(buf => socket.send(buf));
            }
          };

          recorder.start(500); // send chunks every 500ms
          recording = true;
          recordBtn.classList.add("recording");
          recordBtn.textContent = "⏹️";
          statusDiv.textContent = "Recording & streaming... Tap to stop.";
        };

        socket.onmessage = e => logMessage("Server: " + e.data);

      } catch {
        alert("Microphone access denied.");
      }
    } else {
      recorder.stop();
      socket.close();
      recording = false;
      recordBtn.classList.remove("recording");
      recordBtn.textContent = "🎙️";
      statusDiv.textContent = "Stopped. File saved on server.";
      logMessage("❌ Disconnected");
    }
  });

  function logMessage(msg) {
    log.textContent += msg + "\n";
    log.scrollTop = log.scrollHeight;
  }
});
