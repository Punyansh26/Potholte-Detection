/* ═══════════════════════════════════════════════════════════════
   camera.js — Live Camera Detection Module
   Uses browser MediaStream API (getUserMedia) to access phone/webcam,
   sends frames to the backend /stream/video MJPEG endpoint (rendered
   in a hidden <img>), then draws branded overlay on the canvas.

   Detection flow:
     1. getUserMedia → <video> element
     2. Every INFER_INTERVAL ms, draw frame to hidden canvas
     3. POST canvas JPEG to /detections (via backend YOLOv8)
     4. Draw returned bbox annotations on the overlay <canvas>
     5. Show detections in the info panel

   NOTE: The /stream/video endpoint runs server-side YOLO, but for
   the browser camera we run client→server inference via POST /detections.
   This avoids needing the browser to stream raw video to the server.
   ═══════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const API = window.location.origin;
  const INFER_INTERVAL = 800;   // ms between inference calls
  const SEV_COLORS = {
    low:      '#22c55e',
    medium:   '#eab308',
    high:     '#f97316',
    critical: '#ef4444',
  };

  // ── State ──────────────────────────────────────────────────────

  let stream = null;
  let inferTimer = null;
  let facingMode = 'environment';  // rear camera by default
  let totalSent = 0;
  let currentLat = 19.0760;
  let currentLon = 72.8777;

  // ── DOM refs ───────────────────────────────────────────────────

  const video      = document.getElementById('live-video');
  const overlay    = document.getElementById('live-overlay');
  const capCanvas  = document.getElementById('capture-canvas');
  const stage      = document.getElementById('live-stage');
  const placeholder = document.getElementById('live-placeholder');

  const btnStart   = document.getElementById('btn-cam-start');
  const btnStop    = document.getElementById('btn-cam-stop');
  const btnFlip    = document.getElementById('btn-cam-flip');
  const confSlider = document.getElementById('conf-slider');
  const confValue  = document.getElementById('conf-value');

  const badgeEl    = document.getElementById('live-status-badge');
  const statusText = document.getElementById('live-status-text');
  const detCount   = document.getElementById('live-det-count');
  const gpsEl      = document.getElementById('live-gps');
  const totalEl    = document.getElementById('live-total-sent');
  const detList    = document.getElementById('live-det-list');

  // Tab switch awareness — stop camera when leaving Live tab
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.tab !== 'live' && stream) stopCamera();
    });
  });

  // Confidence slider
  confSlider.addEventListener('input', () => {
    confValue.textContent = Math.round(confSlider.value * 100) + '%';
  });

  // GPS from browser
  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(pos => {
      currentLat = pos.coords.latitude;
      currentLon = pos.coords.longitude;
      gpsEl.textContent = `${currentLat.toFixed(5)}, ${currentLon.toFixed(5)}`;
    }, () => {});
  }

  // ── Camera controls ────────────────────────────────────────────

  btnStart.addEventListener('click', startCamera);
  btnStop.addEventListener('click', stopCamera);
  btnFlip.addEventListener('click', flipCamera);

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      video.srcObject = stream;
      video.onloadedmetadata = () => {
        stage.classList.add('video-ready');
        placeholder.classList.add('hidden');

        // Match overlay size to video
        overlay.width  = video.videoWidth;
        overlay.height = video.videoHeight;
        capCanvas.width  = video.videoWidth;
        capCanvas.height = video.videoHeight;

        startInference();
      };

      setBadge('live', '● Live');
      statusText.textContent = 'Camera active — detecting…';
      btnStart.style.display = 'none';
      btnStop.style.display  = '';
      btnFlip.style.display  = '';
    } catch (err) {
      setBadge('error', '● Error');
      statusText.textContent = `Camera error: ${err.message}`;
      showToast('error', `📷 Camera: ${err.message}`);
    }
  }

  function stopCamera() {
    clearInterval(inferTimer);
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    video.srcObject = null;
    stage.classList.remove('video-ready');
    placeholder.classList.remove('hidden');
    clearCanvas();

    setBadge('idle', '● Idle');
    statusText.textContent = 'Camera stopped';
    btnStart.style.display = '';
    btnStop.style.display  = 'none';
    btnFlip.style.display  = 'none';
  }

  async function flipCamera() {
    facingMode = facingMode === 'environment' ? 'user' : 'environment';
    stopCamera();
    await startCamera();
  }

  // ── Inference loop ─────────────────────────────────────────────

  function startInference() {
    inferTimer = setInterval(runInference, INFER_INTERVAL);
  }

  async function runInference() {
    if (!stream || !video.videoWidth) return;

    // Capture frame to canvas
    const ctx = capCanvas.getContext('2d');
    ctx.drawImage(video, 0, 0, capCanvas.width, capCanvas.height);

    // Get base64 JPEG (strip data: prefix)
    const b64 = capCanvas.toDataURL('image/jpeg', 0.8).split(',')[1];

    // POST to /detections — backend runs YOLO and returns result
    try {
      const resp = await fetch(`${API}/detections`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          camera_id: 'browser-cam',
          lat: currentLat,
          lon: currentLon,
          bbox: [],           // server will compute from YOLO
          confidence: parseFloat(confSlider.value),
          snapshot_base64: b64,
        }),
      });

      // Backend returns a single merged result; for bbox display we use
      // the local canvas drawing approach with the server's severity response
      const data = await resp.json();
      if (data && data.pothole_id) {
        totalSent++;
        totalEl.textContent = totalSent;
        detCount.textContent = '1 pothole — ID #' + data.pothole_id;
        addDetectionItem(data);
        // Draw indicator on overlay since we don't have per-frame bbox back
        drawDetectedIndicator(data.severity);
      } else {
        detCount.textContent = '0 detections';
        clearCanvas();
      }
    } catch (err) {
      // Silently skip failed frames
    }
  }

  // ── Canvas drawing ─────────────────────────────────────────────

  function drawDetectedIndicator(severity) {
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    const color = SEV_COLORS[severity] || '#888';

    // Border glow effect
    const grd = ctx.createLinearGradient(0, 0, overlay.width, 0);
    grd.addColorStop(0, color + '80');
    grd.addColorStop(0.5, color + 'dd');
    grd.addColorStop(1, color + '80');

    ctx.strokeStyle = grd;
    ctx.lineWidth = 6;
    ctx.strokeRect(3, 3, overlay.width - 6, overlay.height - 6);

    // Label banner
    ctx.fillStyle = color + 'dd';
    ctx.fillRect(0, 0, overlay.width, 48);
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 26px Inter, sans-serif';
    ctx.fillText(`⚠ Pothole Detected — ${severity.toUpperCase()}`, 16, 34);
  }

  function clearCanvas() {
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    detCount.textContent = '— detections';
  }

  // ── Detection list ─────────────────────────────────────────────

  function addDetectionItem(data) {
    const empty = detList.querySelector('.live-det-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = 'live-det-item';
    item.innerHTML = `
      <div class="det-sev ${data.severity}">${data.severity}</div>
      <div class="det-meta">
        Pothole #${data.pothole_id} &bull; Risk: ${data.risk_score}
        ${data.grievance_filed ? ' &bull; 🚨 Grievance filed' : ''}
      </div>`;
    detList.prepend(item);

    // Keep last 20 items
    while (detList.children.length > 20) detList.lastChild.remove();

    // Toast for critical
    if (data.severity === 'critical') {
      showToast('error', `🚨 Critical pothole detected! Risk: ${data.risk_score}`);
    }
  }

  // ── Helpers ────────────────────────────────────────────────────

  function setBadge(type, text) {
    badgeEl.className = `live-badge ${type}`;
    badgeEl.textContent = text;
  }

  // showToast is defined in app.js — call it if available
  function showToast(type, msg) {
    if (typeof window.showToast === 'function') {
      window.showToast(type, msg);
    }
  }

})();
