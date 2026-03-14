(function () {
  'use strict';

  const statusEl = document.getElementById('phone-status');
  const lastEl = document.getElementById('phone-last');
  const startBtn = document.getElementById('btn-start');
  const stopBtn = document.getElementById('btn-stop');
  const deviceIdInput = document.getElementById('device-id');
  const snapshotInput = document.getElementById('snapshot-url');
  const backendInput = document.getElementById('backend-url');

  let geoWatch = null;
  let latestGeo = null;
  let latestMotion = null;
  let sendTimer = null;

  function apiBase() {
    return backendInput.value.trim() || window.location.origin;
  }

  async function requestMotionPermission() {
    if (typeof DeviceMotionEvent === 'undefined') return true;
    if (typeof DeviceMotionEvent.requestPermission !== 'function') return true;
    const result = await DeviceMotionEvent.requestPermission();
    return result === 'granted';
  }

  function startMotion() {
    window.addEventListener('devicemotion', (event) => {
      const accel = event.accelerationIncludingGravity || event.acceleration || {};
      const rot = event.rotationRate || {};
      latestMotion = {
        accel_x: accel.x,
        accel_y: accel.y,
        accel_z: accel.z,
        gyro_pitch: rot.beta,
        gyro_roll: rot.gamma,
        gyro_yaw: rot.alpha,
      };
    });
  }

  function startGeo() {
    if (!navigator.geolocation) return;
    geoWatch = navigator.geolocation.watchPosition((pos) => {
      latestGeo = {
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        speed_kph: pos.coords.speed != null ? pos.coords.speed * 3.6 : null,
      };
    });
  }

  async function sendPacket() {
    const payload = {
      timestamp: new Date().toISOString(),
      device_id: deviceIdInput.value.trim() || 'phone-001',
      image_url: snapshotInput.value.trim() || null,
      ...(latestMotion || {}),
      ...(latestGeo || {}),
      raw: {},
    };

    try {
      const resp = await fetch(`${apiBase()}/telemetry/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (resp.ok) {
        statusEl.textContent = 'Streaming';
        lastEl.textContent = new Date().toLocaleTimeString();
      }
    } catch {
      statusEl.textContent = 'Offline';
    }
  }

  async function start() {
    const granted = await requestMotionPermission();
    if (!granted) {
      statusEl.textContent = 'Permission needed';
      return;
    }

    startMotion();
    startGeo();

    if (sendTimer) clearInterval(sendTimer);
    sendTimer = setInterval(sendPacket, 1000);
    statusEl.textContent = 'Starting…';

    startBtn.style.display = 'none';
    stopBtn.style.display = '';
  }

  function stop() {
    if (geoWatch) navigator.geolocation.clearWatch(geoWatch);
    if (sendTimer) clearInterval(sendTimer);
    geoWatch = null;
    sendTimer = null;
    statusEl.textContent = 'Stopped';
    startBtn.style.display = '';
    stopBtn.style.display = 'none';
  }

  startBtn.addEventListener('click', start);
  stopBtn.addEventListener('click', stop);
})();
