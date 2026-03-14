/* ═══════════════════════════════════════════════════════════════
   PotholeGuard Dashboard — app.js
   Main application: map, markers, detail panel, reports, verify
   ═══════════════════════════════════════════════════════════════ */

const API = window.location.origin;
const POLL_INTERVAL = 5000; // 5s auto-refresh

// ── State ────────────────────────────────────────────────────────

let map;
let markersLayer;
let potholes = [];
let activeFilter = 'all';
let selectedPothole = null;
let reportMode = false;       // true while picking a location on the map
let reportB64 = null;         // base64 photo for report
let verifyB64 = null;         // base64 photo for verify
let liveStream = null;
let liveFacingMode = 'environment';
let liveDetectionTimer = null;
let liveDetectionPending = false;
let livePositionWatch = null;
let liveGeo = null;

// Severity colors
const SEV_COLORS = {
    low: '#22c55e',
    medium: '#eab308',
    high: '#f97316',
    critical: '#ef4444',
};

// ── Initialize ───────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    bindEvents();
    fetchPotholes();
    setInterval(fetchPotholes, POLL_INTERVAL);
});

function initMap() {
    map = L.map('map', {
        center: [19.076, 72.8777],
        zoom: 13,
        zoomControl: true,
    });

    // Dark-style tiles (CartoDB Dark Matter)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
    }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);

    // Click-to-pin for report mode
    map.on('click', (e) => {
        if (reportMode) {
            document.getElementById('report-lat').value = e.latlng.lat.toFixed(6);
            document.getElementById('report-lon').value = e.latlng.lng.toFixed(6);
            showToast('info', `📍 Location set: ${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)}`);
        }
    });
}

// ── Data fetching ────────────────────────────────────────────────

async function fetchPotholes() {
    try {
        const resp = await fetch(`${API}/potholes`);
        if (!resp.ok) throw new Error(resp.statusText);
        potholes = await resp.json();
        renderMarkers();
        updateStats();
    } catch (err) {
        console.error('Fetch potholes failed:', err);
    }
}

function filteredPotholes() {
    if (activeFilter === 'all') return potholes;
    if (activeFilter === 'repaired') return potholes.filter(p => p.is_repaired);
    return potholes.filter(p => p.severity === activeFilter && !p.is_repaired);
}

// ── Rendering ────────────────────────────────────────────────────

function renderMarkers() {
    markersLayer.clearLayers();
    const visible = filteredPotholes();

    visible.forEach(p => {
        const color = p.is_repaired ? '#06b6d4' : (SEV_COLORS[p.severity] || '#888');
        const radius = p.severity === 'critical' ? 10 : p.severity === 'high' ? 8 : 6;

        const marker = L.circleMarker([p.lat, p.lon], {
            radius,
            fillColor: color,
            fillOpacity: 0.85,
            color: 'rgba(255,255,255,0.4)',
            weight: 2,
            className: 'pothole-marker',
        });

        marker.bindTooltip(
            `<b>#${p.pothole_id}</b> — ${p.severity}${p.is_repaired ? ' ✅' : ''}<br>` +
            `Risk: ${p.risk_score} | Conf: ${(p.avg_confidence * 100).toFixed(0)}%`,
            { className: 'dark-tooltip' }
        );

        marker.on('click', () => openDetail(p));
        markersLayer.addLayer(marker);

        // Pulse ring for critical unrepaired
        if (p.severity === 'critical' && !p.is_repaired) {
            const pulseIcon = L.divIcon({
                html: '<div class="pulse-ring"></div>',
                className: '',
                iconSize: [16, 16],
                iconAnchor: [8, 8],
            });
            const pulseMarker = L.marker([p.lat, p.lon], { icon: pulseIcon, interactive: false });
            markersLayer.addLayer(pulseMarker);
        }
    });
}

function updateStats() {
    const total = potholes.length;
    const critical = potholes.filter(p => p.severity === 'critical' && !p.is_repaired).length;
    const repaired = potholes.filter(p => p.is_repaired).length;
    const pending = total - repaired;

    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-critical').textContent = critical;
    document.getElementById('stat-pending').textContent = pending;
    document.getElementById('stat-repaired').textContent = repaired;

    // Count grievances (approximate — sum detection_count for high+critical)
    const grievances = potholes.reduce((acc, p) => acc + (p.risk_score >= 80 ? 1 : 0), 0);
    document.getElementById('stat-grievances').textContent = grievances;
}

// ── Detail panel ─────────────────────────────────────────────────

async function openDetail(pothole) {
    selectedPothole = pothole;
    const panel = document.getElementById('detail-panel');

    // Fetch full detail (includes grievances)
    try {
        const resp = await fetch(`${API}/potholes/${pothole.pothole_id}`);
        if (resp.ok) {
            const detail = await resp.json();
            pothole = { ...pothole, ...detail };
            selectedPothole = pothole;
        }
    } catch { }

    document.getElementById('detail-title').textContent = `Pothole #${pothole.pothole_id}`;

    const sevBadge = document.getElementById('detail-severity');
    const sevClass = pothole.is_repaired ? 'repaired' : pothole.severity;
    sevBadge.textContent = pothole.is_repaired ? 'Repaired' : pothole.severity;
    sevBadge.className = `severity-badge ${sevClass}`;

    document.getElementById('detail-risk').textContent = pothole.risk_score;
    document.getElementById('detail-location').textContent = `${pothole.lat.toFixed(6)}, ${pothole.lon.toFixed(6)}`;
    document.getElementById('detail-first-seen').textContent = formatTime(pothole.first_seen);
    document.getElementById('detail-last-seen').textContent = formatTime(pothole.last_seen);
    document.getElementById('detail-confidence').textContent = `${(pothole.avg_confidence * 100).toFixed(1)}%`;
    document.getElementById('detail-count').textContent = pothole.detection_count;
    document.getElementById('detail-ultrasonic').textContent = pothole.latest_ultrasonic_distance_cm != null
        ? `${Number(pothole.latest_ultrasonic_distance_cm).toFixed(1)} cm (${pothole.sensor_source || 'demo'})`
        : '—';
    document.getElementById('detail-depth').textContent = pothole.estimated_depth_cm != null
        ? `${Number(pothole.estimated_depth_cm).toFixed(1)} cm`
        : '—';
    document.getElementById('detail-fusion').textContent = pothole.sensor_fusion_score != null
        ? `${Math.round(Number(pothole.sensor_fusion_score) * 100)}% match`
        : '—';
    document.getElementById('detail-description').textContent = pothole.description || '—';

    // Snapshots
    const gallery = document.getElementById('detail-snapshots');
    gallery.innerHTML = '';
    (pothole.snapshots || []).forEach(url => {
        const img = document.createElement('img');
        img.src = url;
        img.alt = 'Pothole snapshot';
        img.loading = 'lazy';
        gallery.appendChild(img);
    });

    // Grievances
    const gList = document.getElementById('detail-grievances');
    gList.innerHTML = '';
    if (pothole.grievances && pothole.grievances.length) {
        const header = document.createElement('label');
        header.textContent = 'Grievances Filed';
        header.style.cssText = 'display:block; font-size:11px; text-transform:uppercase; color:var(--text-secondary); letter-spacing:.6px; margin-bottom:8px;';
        gList.appendChild(header);

        pothole.grievances.forEach(g => {
            const div = document.createElement('div');
            div.className = 'grievance-item';
            div.innerHTML = `
        <div class="ticket-id">${g.grievance_id || 'Pending'}</div>
        <div style="font-size:12px; color:var(--text-secondary); margin-top:4px;">
          ${g.grievance_system} — Status: <b>${g.status}</b>
        </div>
      `;
            gList.appendChild(div);
        });
    }

    panel.classList.add('open');
}

function closeDetail() {
    document.getElementById('detail-panel').classList.remove('open');
    selectedPothole = null;
}

// ── Events ───────────────────────────────────────────────────────

function bindEvents() {
    // ── Tab switching ─────────────────────────────────────────────
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
            // Invalidate map size when switching back to map tab
            if (btn.dataset.tab === 'map' && map) setTimeout(() => map.invalidateSize(), 100);
        });
    });

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeFilter = btn.dataset.filter;
            renderMarkers();
        });
    });

    // Detail panel close
    document.getElementById('close-detail').addEventListener('click', closeDetail);

    // Refresh
    document.getElementById('btn-refresh').addEventListener('click', () => {
        fetchPotholes();
        showToast('info', '🔄 Data refreshed');
    });

    // Report modal
    document.getElementById('btn-report').addEventListener('click', openReportModal);
    document.getElementById('cancel-report').addEventListener('click', closeReportModal);
    document.getElementById('submit-report').addEventListener('click', submitReport);

    // Drop zone (report)
    setupDropZone('drop-zone', 'photo-input', (b64) => { reportB64 = b64; });

    // Verify
    document.getElementById('btn-verify').addEventListener('click', openVerifyModal);
    document.getElementById('cancel-verify').addEventListener('click', closeVerifyModal);
    document.getElementById('submit-verify').addEventListener('click', submitVerify);
    setupDropZone('verify-drop-zone', 'verify-photo-input', (b64) => { verifyB64 = b64; });
}

// ── Report modal ─────────────────────────────────────────────────

function openReportModal() {
    reportMode = true;
    reportB64 = null;
    document.getElementById('report-modal').classList.add('active');
    // Reset form
    document.getElementById('report-lat').value = '';
    document.getElementById('report-lon').value = '';
    document.getElementById('report-desc').value = '';
    document.getElementById('report-severity').value = 'medium';
    resetDropZone('drop-zone');
    showToast('info', '📍 Click on the map to set the pothole location');
}

function closeReportModal() {
    reportMode = false;
    document.getElementById('report-modal').classList.remove('active');
}

async function submitReport() {
    const lat = parseFloat(document.getElementById('report-lat').value);
    const lon = parseFloat(document.getElementById('report-lon').value);
    const severity = document.getElementById('report-severity').value;
    const desc = document.getElementById('report-desc').value;

    if (isNaN(lat) || isNaN(lon)) {
        showToast('error', '❌ Please set a valid location');
        return;
    }

    try {
        const body = { lat, lon, severity, description: desc };
        if (reportB64) body.snapshot_base64 = reportB64;

        const resp = await fetch(`${API}/manual_report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        showToast('success', `✅ Report submitted — Pothole #${data.pothole_id} (${data.is_new ? 'new' : 'merged'})`);
        closeReportModal();
        fetchPotholes();
    } catch (err) {
        showToast('error', `❌ Submit failed: ${err.message}`);
    }
}

// ── Verify modal ─────────────────────────────────────────────────

function openVerifyModal() {
    if (!selectedPothole) return;
    verifyB64 = null;
    document.getElementById('verify-pothole-label').textContent =
        `Pothole #${selectedPothole.pothole_id} — ${selectedPothole.severity}`;
    document.getElementById('verify-modal').classList.add('active');
    resetDropZone('verify-drop-zone');
}

function closeVerifyModal() {
    document.getElementById('verify-modal').classList.remove('active');
}

async function submitVerify() {
    if (!selectedPothole || !verifyB64) {
        showToast('error', '❌ Please attach a new photo');
        return;
    }
    try {
        const resp = await fetch(`${API}/potholes/${selectedPothole.pothole_id}/verify`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ snapshot_base64: verifyB64 }),
        });
        const data = await resp.json();
        const emoji = data.action_taken === 'marked_repaired' ? '✅' : data.action_taken === 'escalated' ? '⚠️' : 'ℹ️';
        showToast(
            data.action_taken === 'marked_repaired' ? 'success' : 'info',
            `${emoji} Verification: ${data.action_taken.replace(/_/g, ' ')} (similarity: ${(data.similarity_score * 100).toFixed(1)}%)`
        );
        closeVerifyModal();
        closeDetail();
        fetchPotholes();
    } catch (err) {
        showToast('error', `❌ Verify failed: ${err.message}`);
    }
}

// ── Drop zone helper ─────────────────────────────────────────────

function setupDropZone(zoneId, inputId, onBase64) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        handleFile(e.dataTransfer.files[0], zone, onBase64);
    });
    input.addEventListener('change', () => {
        if (input.files[0]) handleFile(input.files[0], zone, onBase64);
    });
}

function handleFile(file, zone, onBase64) {
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        const b64 = e.target.result.split(',')[1];
        onBase64(b64);
        zone.innerHTML = `<img src="${e.target.result}" alt="Preview" />`;
    };
    reader.readAsDataURL(file);
}

function resetDropZone(zoneId) {
    document.getElementById(zoneId).innerHTML = 'Click or drag a photo here';
}

// ── Toast ────────────────────────────────────────────────────────

function showToast(type, message) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}
// Expose globally so camera.js can use it
window.showToast = showToast;

// ── Helpers ──────────────────────────────────────────────────────

async function toggleLiveCamera() {
    if (liveStream) {
        stopLiveCamera();
        return;
    }
    await startLiveCamera();
}

async function startLiveCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
        setLiveStatus('error', 'No camera support');
        showToast('error', '❌ This browser does not support live camera capture');
        return;
    }

    if (!isCameraOriginAllowed()) {
        setLiveStatus('error', 'HTTPS required');
        showToast('error', '❌ Phone camera access needs HTTPS or localhost. Use HTTPS or the edge client URL mode.');
        return;
    }

    const video = document.getElementById('live-video');
    const emptyState = document.getElementById('live-empty');

    try {
        setLiveStatus('idle', 'Starting');
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                facingMode: { ideal: liveFacingMode },
                width: { ideal: 1280 },
                height: { ideal: 720 },
            },
        });

        liveStream = stream;
        video.srcObject = stream;
        await video.play();

        emptyState.textContent = 'Camera is live. Detection runs on sampled frames and persists results to the dashboard.';
        document.getElementById('btn-live-toggle').textContent = 'Stop Camera';
        setLiveStatus('live', 'Live');
        startLiveLocationWatch();
        startLiveDetectionLoop();
    } catch (err) {
        setLiveStatus('error', 'Camera blocked');
        showToast('error', `❌ Unable to start camera: ${err.message}`);
    }
}

function stopLiveCamera() {
    if (liveDetectionTimer) {
        clearInterval(liveDetectionTimer);
        liveDetectionTimer = null;
    }
    if (livePositionWatch !== null) {
        navigator.geolocation?.clearWatch(livePositionWatch);
        livePositionWatch = null;
    }
    if (liveStream) {
        liveStream.getTracks().forEach(track => track.stop());
        liveStream = null;
    }

    const video = document.getElementById('live-video');
    const overlay = document.getElementById('live-overlay');
    const stage = document.getElementById('live-stage');
    const ctx = overlay.getContext('2d');

    video.pause();
    video.srcObject = null;
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    stage.classList.remove('video-ready');
    document.getElementById('btn-live-toggle').textContent = 'Start Camera';
    document.getElementById('live-detection-count').textContent = '0 detections';
    document.getElementById('live-location').textContent = 'Using dashboard defaults';
    document.getElementById('live-empty').textContent = 'Start the camera to stream pothole detection. On phones, the dashboard will prefer the rear camera.';
    setLiveStatus('idle', 'Idle');
}

async function switchLiveCamera() {
    liveFacingMode = liveFacingMode === 'environment' ? 'user' : 'environment';
    if (liveStream) {
        stopLiveCamera();
        await startLiveCamera();
    }
}

function startLiveLocationWatch() {
    if (!navigator.geolocation) {
        document.getElementById('live-location').textContent = 'Geolocation unavailable';
        return;
    }
    livePositionWatch = navigator.geolocation.watchPosition(
        (position) => {
            liveGeo = {
                lat: position.coords.latitude,
                lon: position.coords.longitude,
            };
            document.getElementById('live-location').textContent = `${liveGeo.lat.toFixed(5)}, ${liveGeo.lon.toFixed(5)}`;
        },
        () => {
            document.getElementById('live-location').textContent = 'Using dashboard defaults';
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 15000,
        }
    );
}

function startLiveDetectionLoop() {
    if (liveDetectionTimer) clearInterval(liveDetectionTimer);
    liveDetectionTimer = setInterval(runLiveDetection, 1200);
    runLiveDetection();
}

async function runLiveDetection() {
    if (!liveStream || liveDetectionPending) return;

    const video = document.getElementById('live-video');
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;

    const capture = document.getElementById('live-capture');
    const context = capture.getContext('2d');
    const aspect = video.videoHeight / video.videoWidth;
    const width = 640;
    const height = Math.max(360, Math.round(width * aspect));

    capture.width = width;
    capture.height = height;
    context.drawImage(video, 0, 0, width, height);

    const imageBase64 = capture.toDataURL('image/jpeg', 0.72).split(',')[1];
    const lat = liveGeo?.lat ?? 19.076;
    const lon = liveGeo?.lon ?? 72.8777;

    liveDetectionPending = true;
    try {
        const resp = await fetch(`${API}/live/detect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_base64: imageBase64,
                camera_id: `browser-${liveFacingMode}`,
                lat,
                lon,
                persist: true,
            }),
        });

        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || resp.statusText);

        drawLiveDetections(data.detections || [], data.frame_width || width, data.frame_height || height);
        const count = (data.detections || []).length;
        document.getElementById('live-detection-count').textContent = `${count} detection${count === 1 ? '' : 's'}`;
    } catch (err) {
        setLiveStatus('error', 'Detection error');
        document.getElementById('live-detection-count').textContent = 'Detection paused';
        showToast('error', `❌ Live detection failed: ${err.message}`);
        stopLiveCamera();
    } finally {
        liveDetectionPending = false;
    }
}

function drawLiveDetections(detections, frameWidth, frameHeight) {
    const overlay = document.getElementById('live-overlay');
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    const scaleX = overlay.width / frameWidth;
    const scaleY = overlay.height / frameHeight;

    detections.forEach(det => {
        const [x1, y1, x2, y2] = det.bbox || [0, 0, 0, 0];
        const boxX = x1 * scaleX;
        const boxY = y1 * scaleY;
        const boxW = (x2 - x1) * scaleX;
        const boxH = (y2 - y1) * scaleY;
        const color = SEV_COLORS[det.severity_est] || '#22d3ee';

        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(boxX, boxY, boxW, boxH);

        const label = `${det.severity_est || 'pothole'} ${(det.confidence * 100).toFixed(0)}%${det.pothole_id ? ` • #${det.pothole_id}` : ''}`;
        ctx.font = '600 14px Inter, system-ui, sans-serif';
        const labelWidth = ctx.measureText(label).width + 18;
        const labelY = Math.max(24, boxY - 10);

        ctx.fillStyle = color;
        ctx.fillRect(boxX, labelY - 18, labelWidth, 24);
        ctx.fillStyle = '#050816';
        ctx.fillText(label, boxX + 9, labelY - 2);
    });
}

function syncLiveOverlaySize() {
    const overlay = document.getElementById('live-overlay');
    const stage = document.getElementById('live-stage');
    const rect = stage.getBoundingClientRect();
    overlay.width = rect.width;
    overlay.height = rect.height;
}

function setLiveStatus(kind, label) {
    const status = document.getElementById('live-status');
    status.textContent = label;
    status.className = `live-status ${kind}`;
}

function isCameraOriginAllowed() {
    return window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
}

function formatTime(ts) {
    if (!ts) return '—';
    try {
        const d = new Date(ts);
        return d.toLocaleString();
    } catch { return ts; }
}
