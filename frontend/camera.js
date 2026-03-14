/* ═══════════════════════════════════════════════════════════════
   camera.js — IP Webcam Live Detection Module

   Flow:
     1. User enters IP Webcam URL (e.g. http://192.168.0.103:8080/video)
     2. We build the backend MJPEG stream URL:
          /stream/video?source=<url>&conf=0.25&skip=2
     3. Set <img id="live-stream-img"> src to that URL
     4. Backend (stream.py) pulls frames from the phone, runs YOLOv8,
        draws bounding boxes, and streams annotated MJPEG back
     5. Poll /potholes every 5s to update the detections list
   ═══════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const API = window.location.origin;

  // ── DOM refs ───────────────────────────────────────────────────
  const streamImg   = document.getElementById('live-stream-img');
  const placeholder = document.getElementById('live-placeholder');
  const stage       = document.getElementById('live-stage');

  const btnStart    = document.getElementById('btn-cam-start');
  const btnStop     = document.getElementById('btn-cam-stop');
  const camUrlInput = document.getElementById('cam-url');
  const confSlider  = document.getElementById('conf-slider');
  const confValue   = document.getElementById('conf-value');
  const skipSlider  = document.getElementById('skip-slider');
  const skipValue   = document.getElementById('skip-value');
  const sensorMode  = document.getElementById('sensor-mode');

  const badgeEl     = document.getElementById('live-status-badge');
  const statusText  = document.getElementById('live-status-text');
  const detCountEl  = document.getElementById('live-det-count');
  const gpsEl       = document.getElementById('live-gps');
  const totalEl     = document.getElementById('live-total-sent');
  const detList     = document.getElementById('live-det-list');

  const sensorSourceEl     = document.getElementById('sensor-source');
  const sensorVibrationEl  = document.getElementById('sensor-vibration');
  const sensorPeakEl       = document.getElementById('sensor-peak');
  const sensorShockEl      = document.getElementById('sensor-shock');
  const sensorRoughnessEl  = document.getElementById('sensor-roughness');
  const sensorClearanceEl  = document.getElementById('sensor-clearance');
  const sensorDepthEl      = document.getElementById('sensor-depth');
  const sensorFusionEl     = document.getElementById('sensor-fusion');
  const sensorSeverityEl   = document.getElementById('sensor-severity');
  const sensorSpeedEl      = document.getElementById('sensor-speed');
  const sensorAltitudeEl   = document.getElementById('sensor-altitude');
  const sensorAttitudeEl   = document.getElementById('sensor-attitude');
  const sensorYawEl        = document.getElementById('sensor-yaw');
  const sensorAdvisoryEl   = document.getElementById('sensor-advisory');

  let pollTimer     = null;
  let telemetryTimer = null;
  let lastKnownIds  = new Set();
  let connected     = false;

  // ── Sliders ─────────────────────────────────────────────────────
  confSlider.addEventListener('input', () => {
    confValue.textContent = Math.round(confSlider.value * 100) + '%';
    if (connected) reconnect();   // update stream params live
  });
  skipSlider.addEventListener('input', () => {
    skipValue.textContent = skipSlider.value;
    if (connected) reconnect();
  });
  sensorMode.addEventListener('change', () => {
    if (connected) reconnect();
    pollTelemetry();
  });

  // ── Connect / Disconnect ────────────────────────────────────────
  btnStart.addEventListener('click', connect);
  btnStop.addEventListener('click', disconnect);

  function buildStreamUrl() {
    const src  = camUrlInput.value.trim() || 'http://192.168.0.103:8080/video';
    const conf = confSlider.value;
    const skip = skipSlider.value;
    const mode = sensorMode.value;
    return `${API}/stream/video?source=${encodeURIComponent(src)}&conf=${conf}&skip=${skip}&post=true&mode=${encodeURIComponent(mode)}`;
  }

  function buildTelemetryUrl() {
    return `${API}/stream/telemetry?mode=${encodeURIComponent(sensorMode.value)}`;
  }

  function connect() {
    const src = camUrlInput.value.trim();
    if (!src) { toast('error', '❌ Enter the IP Webcam URL first'); return; }

    setBadge('live', '● Connecting…');
    statusText.textContent = 'Connecting to ' + src;

    // Set the img src — browser requests MJPEG from backend
    streamImg.src = buildStreamUrl();
    streamImg.style.display = 'block';
    placeholder.classList.add('hidden');

    streamImg.onload = () => {
      // First frame received — we're live
      connected = true;
      setBadge('live', '● Live');
      statusText.textContent = 'Streaming from phone';
      btnStart.style.display = 'none';
      btnStop.style.display  = '';
      camUrlInput.disabled   = true;
      startPolling();
      startTelemetryPolling();
    };

    streamImg.onerror = () => {
      // Stream failed
      setBadge('error', '● Error');
      statusText.textContent = 'Cannot connect — check URL & backend';
      toast('error', '❌ Stream failed. Is the backend running and the phone on the same Wi-Fi?');
      streamImg.src = '';
      streamImg.style.display = 'none';
      placeholder.classList.remove('hidden');
      connected = false;
      stopTelemetryPolling();
      resetTelemetry();
    };
  }

  function disconnect() {
    connected = false;
    streamImg.src = '';
    streamImg.style.display = 'none';
    placeholder.classList.remove('hidden');
    stopPolling();
    stopTelemetryPolling();
    setBadge('idle', '● Idle');
    statusText.textContent  = 'Disconnected';
    detCountEl.textContent  = '— detections';
    btnStart.style.display  = '';
    btnStop.style.display   = 'none';
    camUrlInput.disabled    = false;
    resetTelemetry();
  }

  function reconnect() {
    if (!connected) return;
    streamImg.src = buildStreamUrl();
  }

  // ── GPS ─────────────────────────────────────────────────────────
  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(pos => {
      gpsEl.textContent = `${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}`;
    }, () => { gpsEl.textContent = 'Dashboard defaults'; });
  }

  // ── Poll /potholes to update detection list ─────────────────────
  function startPolling() {
    stopPolling();
    pollTimer = setInterval(pollDetections, 3000);
    pollDetections(); // immediate first call
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function startTelemetryPolling() {
    stopTelemetryPolling();
    telemetryTimer = setInterval(pollTelemetry, 1500);
    pollTelemetry();
  }

  function stopTelemetryPolling() {
    if (telemetryTimer) { clearInterval(telemetryTimer); telemetryTimer = null; }
  }

  async function pollDetections() {
    try {
      const resp = await fetch(`${API}/potholes`);
      const data = await resp.json();
      const newOnes = data.filter(p => !lastKnownIds.has(p.pothole_id));
      newOnes.forEach(p => {
        lastKnownIds.add(p.pothole_id);
        addDetectionItem(p);
      });
      // Update count with last-5s detections (approximate via detection_count delta)
      const total = data.length;
      detCountEl.textContent = `${total} pothole${total !== 1 ? 's' : ''} in DB`;
      totalEl.textContent    = total;
    } catch { /* silently skip */ }
  }

  async function pollTelemetry() {
    try {
      const resp = await fetch(buildTelemetryUrl());
      if (!resp.ok) throw new Error('Telemetry unavailable');
      const data = await resp.json();
      renderTelemetry(data.telemetry || {});
    } catch {
      if (!connected) resetTelemetry();
    }
  }

  function addDetectionItem(p) {
    const empty = detList.querySelector('.live-det-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = 'live-det-item';
    item.innerHTML = `
      <div class="det-sev ${p.severity}">${p.severity}</div>
      <div class="det-meta">
        Pothole #${p.pothole_id} &bull; Risk: ${p.risk_score}
        ${p.risk_score >= 80 ? ' &bull; 🚨 Grievance filed' : ''}
      </div>`;
    detList.prepend(item);
    while (detList.children.length > 20) detList.lastChild.remove();

    if (p.severity === 'critical') {
      toast('error', `🚨 Critical pothole #${p.pothole_id} detected (risk ${p.risk_score})`);
    }
  }

  function renderTelemetry(telemetry) {
    sensorSourceEl.textContent = telemetry.sensor_source || 'demo-sensor-rig';
    sensorVibrationEl.textContent = `${fmtNumber(telemetry.vibration_rms_g, 2)} g`;
    sensorPeakEl.textContent = `Peak ${fmtNumber(telemetry.peak_accel_g, 2)} g`;
    sensorShockEl.textContent = `${telemetry.shock_index ?? 0}`;
    sensorRoughnessEl.textContent = `Roughness ${fmtNumber(telemetry.roughness_index, 1)}`;
    sensorClearanceEl.textContent = telemetry.ultrasonic_distance_cm != null
      ? `${fmtNumber(telemetry.ultrasonic_distance_cm, 1)} cm`
      : '--';
    sensorDepthEl.textContent = telemetry.estimated_depth_cm != null
      ? `Depth ${fmtNumber(telemetry.estimated_depth_cm, 1)} cm`
      : 'Depth --';
    sensorFusionEl.textContent = telemetry.sensor_fusion_score != null
      ? `${Math.round(Number(telemetry.sensor_fusion_score) * 100)}%`
      : '--';
    sensorSeverityEl.textContent = `Severity ${telemetry.max_severity || 'none'}`;
    sensorSpeedEl.textContent = telemetry.speed_kph != null
      ? `${fmtNumber(telemetry.speed_kph, 1)} km/h`
      : '--';
    sensorAltitudeEl.textContent = telemetry.altitude_m != null
      ? `Altitude ${fmtNumber(telemetry.altitude_m, 1)} m`
      : 'Altitude ground';
    sensorAttitudeEl.textContent = `P ${fmtNumber(telemetry.pitch_deg, 1)}° / R ${fmtNumber(telemetry.roll_deg, 1)}°`;
    sensorYawEl.textContent = `Yaw ${fmtNumber(telemetry.yaw_deg, 1)}°`;
    sensorAdvisoryEl.textContent = telemetry.advisory || 'Monitoring road surface';
  }

  function resetTelemetry() {
    renderTelemetry({
      sensor_source: 'demo-sensor-rig',
      vibration_rms_g: 0,
      peak_accel_g: 0,
      shock_index: 0,
      roughness_index: 0,
      max_severity: 'none',
      advisory: 'Monitoring road surface',
    });
  }

  function fmtNumber(value, digits) {
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(digits) : Number(0).toFixed(digits);
  }

  // ── Helpers ─────────────────────────────────────────────────────
  function setBadge(type, text) {
    badgeEl.className = `live-badge ${type}`;
    badgeEl.textContent = text;
  }

  function toast(type, msg) {
    if (typeof window.showToast === 'function') window.showToast(type, msg);
  }

  resetTelemetry();

})();
