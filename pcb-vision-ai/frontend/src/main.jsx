import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  Camera,
  Database,
  FileText,
  Gauge,
  History,
  LayoutDashboard,
  Radio,
  Settings,
  ShieldCheck,
  Sparkles,
  XCircle,
  Zap,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import './styles.css';

// Use relative URL so it works on Pi via IP or localhost (Vite proxies /api → backend)
const API = '';

function App() {
  const [page, setPage] = useState('dashboard');
  const [connected, setConnected] = useState(false);
  const [edgeInfo, setEdgeInfo] = useState({ model: '—', labels: [], error: null });
  const [live, setLive] = useState(false);
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({ total: 0, defective: 0, good: 0, defects: {} });
  const [latest, setLatest] = useState(null);
  const [annotatedSrc, setAnnotatedSrc] = useState(null);
  const [previewSrc, setPreviewSrc] = useState(null);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const canvasRef = useRef(null);
  const previewTimer = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [hRes, sRes, cRes] = await Promise.all([
        fetch(`${API}/api/inspections`),
        fetch(`${API}/api/analytics`),
        fetch(`${API}/api/edge/status`),
      ]);
      if (hRes.ok) setHistory(await hRes.json());
      if (sRes.ok) setStats(await sRes.json());
      if (cRes.ok) {
        const st = await cRes.json();
        setConnected(!!st.connected);
        setEdgeInfo({ model: st.model || '—', labels: st.labels || [], error: st.error });
      }
    } catch {
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  async function runDemo() {
    setBusy(true);
    setStatusMsg('Running demo…');
    try {
      const r = await fetch(`${API}/api/demo`, { method: 'POST' });
      if (r.ok) {
        const data = await r.json();
        setLatest(data);
        await refresh();
        setStatusMsg('Demo inspection saved');
      }
    } catch (e) {
      setStatusMsg('Demo failed – is backend running?');
    }
    setBusy(false);
  }

  // Continuous live: MJPEG stream with real Edge Impulse boxes (always on)
  function startCamera() {
    setAnnotatedSrc(null);
    setLive(true);
    // Conveyor ON only while live detection is active
    fetch(`${API}/api/hardware/conveyor/start`, { method: 'POST' }).catch(() => {});
    setPreviewSrc(`${API}/api/camera/live?t=${Date.now()}`);
    setStatusMsg('LIVE detection ON — conveyor running');
    if (previewTimer.current) clearInterval(previewTimer.current);
    previewTimer.current = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/camera/live-status`);
        if (r.ok) {
          const st = await r.json();
          if (st.latest) setLatest(st.latest);
        }
      } catch {
        /* ignore */
      }
    }, 1000);
  }

  function stopCamera() {
    setLive(false);
    setPreviewSrc(null);
    // Conveyor OFF when live detection stops
    fetch(`${API}/api/hardware/conveyor/stop`, { method: 'POST' }).catch(() => {});
    if (previewTimer.current) {
      clearInterval(previewTimer.current);
      previewTimer.current = null;
    }
    setStatusMsg('Live detection stopped — conveyor OFF');
  }

  async function captureAndInfer() {
    setBusy(true);
    setStatusMsg('Single capture + Edge Impulse…');
    try {
      const r = await fetch(`${API}/api/camera/infer`, { method: 'POST' });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      setLatest(data);
      if (data.annotated_jpeg_b64) {
        setAnnotatedSrc('data:image/jpeg;base64,' + data.annotated_jpeg_b64);
      }
      await refresh();
      setStatusMsg(
        data.detections?.length
          ? `Found ${data.detections.length} defect(s) in ${data.inference_ms} ms`
          : `No defects – ${data.inference_ms} ms`
      );
    } catch (e) {
      setStatusMsg(`Inference error: ${e.message}`);
    }
    setBusy(false);
  }

  const pages = [
    ['dashboard', 'Dashboard', LayoutDashboard],
    ['inspection', 'Live Inspection', Camera],
    ['edge', 'Edge Impulse Live', Radio],
    ['history', 'Inspection History', History],
    ['analytics', 'Analytics', Gauge],
    ['documentation', 'Project Report', FileText],
  ];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandmark">
            <Sparkles size={19} />
          </div>
          <div>
            <b>PCB Vision AI</b>
            <span>Inspection Platform</span>
          </div>
        </div>
        <nav>
          {pages.map(([id, label, Icon]) => (
            <button
              key={id}
              className={page === id ? 'nav active' : 'nav'}
              onClick={() => setPage(id)}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebottom">
          <div className={'connection ' + (connected ? 'ok' : 'offline')}>
            <span />
            <div>
              <small>AI Engine</small>
              <b>{connected ? 'Edge Impulse connected' : 'Model not loaded'}</b>
            </div>
          </div>
          <button className="nav" disabled>
            <Settings size={18} />
            Settings
          </button>
        </div>
      </aside>

      <main>
        <header>
          <div>
            <div className="eyebrow">INDUSTRIAL COMPUTER VISION</div>
            <h1>
              {page === 'dashboard' && 'Inspection Command Center'}
              {page === 'inspection' && 'Live PCB Inspection'}
              {page === 'edge' && 'Edge Impulse Live Links'}
              {page === 'history' && 'Inspection History'}
              {page === 'analytics' && 'Inspection Analytics'}
              {page === 'documentation' && 'Project Documentation'}
            </h1>
          </div>
          <div className="topstatus">
            <Radio size={16} />
            <span>{connected ? `Edge Impulse · ${edgeInfo.model}` : 'Waiting for model.eim'}</span>
          </div>
        </header>

        {statusMsg && <div className="toast">{statusMsg}</div>}

        {page === 'dashboard' && (
          <Dashboard
            stats={stats}
            latest={latest}
            setPage={setPage}
            runDemo={runDemo}
            connected={connected}
            edgeInfo={edgeInfo}
            busy={busy}
          />
        )}
        {page === 'inspection' && (
          <Inspection
            live={live}
            previewSrc={previewSrc}
            startCamera={startCamera}
            stopCamera={stopCamera}
            captureAndInfer={captureAndInfer}
            runDemo={runDemo}
            latest={latest}
            annotatedSrc={annotatedSrc}
            clearAnnotated={() => setAnnotatedSrc(null)}
            busy={busy}
            connected={connected}
          />
        )}
        {page === 'edge' && <EdgeLinks live={live} startCamera={startCamera} />}
        {page === 'history' && <HistoryPage history={history} />}
        {page === 'analytics' && <Analytics stats={stats} />}
        {page === 'documentation' && <Documentation />}
      </main>
    </div>
  );
}

function Dashboard({ stats, latest, setPage, runDemo, connected, edgeInfo, busy }) {
  return (
    <section className="content">
      <div className="hero">
        <div>
          <div className="pill">
            <ShieldCheck size={14} /> AI-powered quality control
          </div>
          <h2>See PCB defects before they become production problems.</h2>
          <p>
            Real-time visual inspection powered by your Edge Impulse model on Raspberry Pi 4,
            with full inspection history and analytics.
          </p>
          <div className="actions">
            <button className="primary" onClick={() => setPage('inspection')}>
              <Camera size={17} /> Open live inspection
            </button>
            <button className="secondary" onClick={runDemo} disabled={busy}>
              <Activity size={17} /> Run demo inspection
            </button>
          </div>
        </div>
        <div className="hero-art">
          <div className="scanline" />
          <div className="pcb-card">
            <span>YOLO / FOMO</span>
            <strong>PCB</strong>
            <i>AI VISION</i>
          </div>
        </div>
      </div>

      <div className="stats">
        {[
          ['Total inspections', stats.total, Database],
          ['Defective boards', stats.defective, XCircle],
          ['Good inspections', stats.good, ShieldCheck],
          ['Defect types', Object.keys(stats.defects || {}).length, Activity],
        ].map(([label, value, Icon]) => (
          <div className="stat" key={label}>
            <Icon size={19} />
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panelhead">
            <div>
              <small>MODEL PIPELINE</small>
              <h3>Inspection flow</h3>
            </div>
            <span className="tag">{connected ? 'LIVE' : 'STANDBY'}</span>
          </div>
          <div className="pipeline">
            <Node t="Camera" />
            <em>→</em>
            <Node t="Edge AI" />
            <em>→</em>
            <Node t="Decision" />
            <em>→</em>
            <Node t="Database" />
          </div>
          <div className="model-info">
            <div>
              <span>Status</span>
              <b className={connected ? 'good' : 'bad'}>
                {connected ? 'Connected' : 'Not loaded'}
              </b>
            </div>
            <div>
              <span>Model</span>
              <b>{edgeInfo.model}</b>
            </div>
            <div>
              <span>Labels</span>
              <b>{edgeInfo.labels?.length ? edgeInfo.labels.join(', ') : '—'}</b>
            </div>
          </div>
          {edgeInfo.error && (
            <div className="err-box">
              <AlertTriangle size={14} /> {edgeInfo.error}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panelhead">
            <div>
              <small>LATEST RESULT</small>
              <h3>{latest ? latest.image_name : 'No inspection yet'}</h3>
            </div>
          </div>
          {latest ? (
            <Result result={latest} />
          ) : (
            <div className="empty">
              Run a demo or open Live Inspection to populate this panel.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Node({ t }) {
  return (
    <div className="node">
      <span />
      {t}
    </div>
  );
}

function Inspection({
  live,
  previewSrc,
  startCamera,
  stopCamera,
  captureAndInfer,
  runDemo,
  latest,
  annotatedSrc,
  clearAnnotated,
  busy,
  connected,
}) {
  return (
    <section className="content">
      <div className="inspection-grid">
        <div className="panel camera-panel">
          <div className="panelhead">
            <div>
              <small>CONTINUOUS LIVE DETECTION</small>
              <h3>Pi camera + Edge Impulse (always on)</h3>
            </div>
            <span className={live ? 'live' : 'tag'}>{live ? '● LIVE DETECTING' : 'STOPPED'}</span>
          </div>
          <div className="viewport">
            {live && previewSrc ? (
              <img
                src={previewSrc}
                alt="Live Edge Impulse detection stream"
                className="annotated-img"
              />
            ) : annotatedSrc ? (
              <img src={annotatedSrc} alt="Last detection" className="annotated-img" />
            ) : (
              <div className="camera-placeholder">
                <Camera size={48} />
                <b>Start live detection</b>
                <span>
                  Press Start — camera stays on and Edge Impulse runs continuously with
                  bounding boxes (no click per frame).
                </span>
              </div>
            )}
            <div className="overlay tl" />
            <div className="overlay br" />
          </div>
          <div className="camera-actions">
            <button className="primary" onClick={live ? stopCamera : startCamera} disabled={!connected && !live}>
              {live ? 'Stop live detection' : 'Start live detection'}
            </button>
            <button
              className="secondary"
              onClick={captureAndInfer}
              disabled={busy || !connected}
            >
              <Zap size={17} /> Single shot
            </button>
          </div>
        </div>

        <div className="panel">
          <div className="panelhead">
            <div>
              <small>AI OUTPUT (LIVE)</small>
              <h3>Current detections</h3>
            </div>
          </div>
          {latest ? (
            <Result result={latest} />
          ) : (
            <div className="empty">
              Start live detection — real model results appear here continuously.
            </div>
          )}
          <div className="metricrow">
            <div>
              <span>Model</span>
              <b>Edge Impulse</b>
            </div>
            <div>
              <span>Latency</span>
              <b>{latest?.inference_ms != null ? `${latest.inference_ms} ms` : '—'}</b>
            </div>
            <div>
              <span>Mode</span>
              <b>{live ? 'Continuous' : 'Idle'}</b>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function EdgeLinks({ live, startCamera }) {
  const studio = 'https://studio.edgeimpulse.com/studio/1094555';
  const studioLive = 'https://studio.edgeimpulse.com/studio/1094555/live';
  const classifier =
    'https://smartphone.edgeimpulse.com/classifier.html?publicProjectId=1094555';
  const localLive = `${window.location.origin}/api/camera/live`;
  const qrEdge = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(classifier)}`;
  const qrLocal = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(window.location.origin)}`;

  return (
    <section className="content">
      <div className="hero">
        <div>
          <div className="pill">
            <Radio size={14} /> Edge Impulse project 1094555
          </div>
          <h2>Live detection linked to your Edge Impulse project</h2>
          <p>
            Pi live stream uses your deployed <b>model.eim</b> from project 1094555 (same labels:
            good, defects, and <b>Unknown_PCB</b> when the board is not in the trained dataset).
            Optional: scan the QR on a phone to open Edge Impulse mobile classification for this project.
          </p>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panelhead">
            <div>
              <small>ON THIS WEBSITE (PI + model.eim)</small>
              <h3>Local continuous stream</h3>
            </div>
            <span className={live ? 'live' : 'tag'}>{live ? '● LIVE' : 'OFF'}</span>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.5 }}>
            USB camera on the Pi → Edge Impulse <b>.eim</b> → boxes + decision
            (GOOD / DEFECT / <b>Unknown_PCB</b>). Conveyor runs only while live is on.
          </p>
          <div className="camera-actions" style={{ marginTop: 12 }}>
            <button className="accent" onClick={startCamera}>
              <Camera size={17} /> Start Live Inspection
            </button>
            <a className="secondary" href={localLive} target="_blank" rel="noreferrer" style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 8, padding: '11px 18px', borderRadius: 11, border: '1px solid var(--line)' }}>
              Direct stream URL
            </a>
          </div>
          <div className="empty" style={{ marginTop: 14, textAlign: 'left' }}>
            Stream URL:<br />
            <code style={{ color: 'var(--cyan)', wordBreak: 'break-all' }}>{localLive}</code>
          </div>
        </div>

        <div className="panel">
          <div className="panelhead">
            <div>
              <small>EDGE IMPULSE (project 1094555)</small>
              <h3>Studio, live & phone</h3>
            </div>
          </div>
          <div className="model-info">
            <div>
              <span>Project studio</span>
              <b>
                <a href={studio} target="_blank" rel="noreferrer" style={{ color: 'var(--cyan)' }}>
                  studio.edgeimpulse.com/studio/1094555 ↗
                </a>
              </b>
            </div>
            <div>
              <span>Studio live classification</span>
              <b>
                <a href={studioLive} target="_blank" rel="noreferrer" style={{ color: 'var(--cyan)' }}>
                  Open live in Studio ↗
                </a>
              </b>
            </div>
            <div>
              <span>Phone classifier (this project)</span>
              <b>
                <a href={classifier} target="_blank" rel="noreferrer" style={{ color: 'var(--cyan)' }}>
                  Mobile Edge Impulse client ↗
                </a>
              </b>
            </div>
          </div>
          <div className="empty" style={{ marginTop: 14, textAlign: 'left', fontSize: 13 }}>
            <b>Unknown_PCB:</b> shown only when the model returns mid-confidence boxes but no
            trained class is strong enough (untrained board). Empty belt stays &quot;NO DEFECT DETECTED&quot;.
          </div>
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 16 }}>
        <div className="panel">
          <div className="panelhead">
            <div>
              <small>OPTIONAL</small>
              <h3>QR — phone Edge Impulse detection</h3>
            </div>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.5 }}>
            Scan with your phone camera to open the Edge Impulse classifier for project <b>1094555</b>.
            Phone uses its own camera in the browser (separate from the Pi belt camera).
          </p>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
            <img src={qrEdge} alt="QR Edge Impulse mobile classifier" width={160} height={160} style={{ borderRadius: 12, background: '#fff', padding: 8 }} />
            <div style={{ fontSize: 13, color: 'var(--muted)', maxWidth: 280 }}>
              Opens:<br />
              <code style={{ color: 'var(--cyan)', wordBreak: 'break-all' }}>{classifier}</code>
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panelhead">
            <div>
              <small>OPTIONAL</small>
              <h3>QR — open this dashboard on phone</h3>
            </div>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.5 }}>
            Scan to open the Pi website on your phone (same Wi‑Fi as the Pi). Live stream still uses the Pi USB camera.
          </p>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
            <img src={qrLocal} alt="QR local dashboard" width={160} height={160} style={{ borderRadius: 12, background: '#fff', padding: 8 }} />
            <div style={{ fontSize: 13, color: 'var(--muted)', maxWidth: 280 }}>
              Opens:<br />
              <code style={{ color: 'var(--cyan)', wordBreak: 'break-all' }}>{window.location.origin}</code>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

const GOOD_LABELS = new Set(['pcb_good', 'good', 'ok', 'pass', 'no_defect']);

function isGoodLabel(name) {
  return GOOD_LABELS.has(String(name || '').toLowerCase());
}

function Result({ result }) {
  // Use decision from backend (trained labels) when available
  const decision =
    result.decision ||
    (result.detections?.some((d) => !isGoodLabel(d.class_name))
      ? 'DEFECT DETECTED'
      : result.detections?.length
        ? 'GOOD BOARD'
        : 'NO DEFECT DETECTED');
  const dUpper = String(decision).toUpperCase();
  const isUnknown = dUpper.includes('UNKNOWN');
  const isBad = dUpper.startsWith('DEFECT') || isUnknown;

  return (
    <div className="result-block">
      {result.detections?.map((d, i) => (
        <div className={'det' + (isGoodLabel(d.class_name) ? ' good-det' : '')} key={i}>
          <div>
            <b>{d.class_name}</b>
            <span>
              {(d.confidence * 100).toFixed(0)}% confidence
              {d.width > 0 && ` · ${d.x},${d.y} ${d.width}×${d.height}`}
              {isGoodLabel(d.class_name) ? ' · good class' : ' · defect class'}
            </span>
          </div>
          <strong>{(d.confidence * 100).toFixed(0)}%</strong>
        </div>
      ))}
      {isUnknown && (
        <div className="det">
          <div>
            <b>Unknown_PCB</b>
            <span>Board not matching trained classes (low confidence or out of dataset)</span>
          </div>
          <AlertTriangle size={20} />
        </div>
      )}
      {!result.detections?.length && !isUnknown && (
        <div className="det good-det">
          <div>
            <b>No objects from model</b>
            <span>Model returned no boxes (empty view or clear belt)</span>
          </div>
          <CheckCircle2 size={20} />
        </div>
      )}
      <div className={'decision ' + (isBad ? 'bad' : 'good')}>
        <span>INSPECTION DECISION (from your EI labels)</span>
        <b>{isUnknown ? 'Unknown_PCB' : decision}</b>
      </div>
      {result.inference_ms != null && (
        <div className="latency">
          Latency: {result.inference_ms} ms · Source: {result.source || 'edge-impulse'}
        </div>
      )}
    </div>
  );
}

function HistoryPage({ history }) {
  return (
    <section className="content">
      <div className="panel">
        <div className="panelhead">
          <div>
            <small>TRACEABILITY</small>
            <h3>Inspection history</h3>
          </div>
          <span className="tag">{history.length} records</span>
        </div>
        <div className="table">
          <div className="tr th">
            <span>Time</span>
            <span>Source</span>
            <span>Detections</span>
            <span>Decision</span>
            <span>Latency</span>
          </div>
          {history.length ? (
            history.map((x) => (
              <div className="tr" key={x.id}>
                <span>{new Date(x.timestamp).toLocaleString()}</span>
                <span>{x.source}</span>
                <span>
                  {x.detections?.map((d) => d.class_name).join(', ') || '—'}
                </span>
                <span className={(() => { const d = String(x.decision || '').toUpperCase(); return d.startsWith('DEFECT') || d.includes('UNKNOWN') ? 'bad' : 'good'; })()}>
                  {x.decision}
                </span>
                <span>{x.inference_ms} ms</span>
              </div>
            ))
          ) : (
            <div className="empty">No inspection records yet. Run a live or demo inspection.</div>
          )}
        </div>
      </div>
    </section>
  );
}

function Analytics({ stats }) {
  const entries = Object.entries(stats.defects || {});
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <section className="content">
      <div className="stats">
        {[
          ['Total inspections', stats.total],
          ['Defective boards', stats.defective],
          ['Good inspections', stats.good],
          ['Defect types', entries.length],
        ].map(([label, value]) => (
          <div className="stat" key={label}>
            <Activity size={19} />
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
      </div>
      <div className="panel">
        <div className="panelhead">
          <div>
            <small>DEFECT DISTRIBUTION</small>
            <h3>Detected defect classes</h3>
          </div>
        </div>
        {entries.length ? (
          entries.map(([k, v]) => (
            <div className="bar" key={k}>
              <div>
                <span>{k}</span>
                <b>{v}</b>
              </div>
              <i>
                <em style={{ width: `${(v / max) * 100}%` }} />
              </i>
            </div>
          ))
        ) : (
          <div className="empty">Analytics will populate as inspections are stored.</div>
        )}
      </div>
    </section>
  );
}

function Documentation() {
  const team = [
    { name: 'Chiranthan Gowda S P', usn: '1RF24EC400' },
    { name: 'Mohammed Affan', usn: '1RF24EC401' },
    { name: 'Pughal P', usn: '1RF24EC403' },
    { name: 'Veeresha M', usn: '1RF24EC405' },
  ];

  return (
    <section className="content report-page">
      <div className="hero dochero">
        <div>
          <div className="pill">
            <FileText size={14} /> Final project report
          </div>
          <h2>Edge-AI Inspection and Conveyor-Based Segregation of Defective PCBs on Raspberry Pi 4</h2>
          <p>
            Team 13 · Dept. of ECE · RV Institute of Technology and Management, Bengaluru · Guided by Dr. Chethan K S
          </p>
        </div>
      </div>

      <div className="report-stack">
        <article className="report-card">
          <h3>01 · Abstract</h3>
          <p>
            Printed circuit boards with missing parts, damaged tracks or soldering faults must be found and
            separated quickly, yet manual visual checking is slow and inconsistent. This project implements a
            low-cost edge prototype: a camera above a motor-driven belt feeds frames to a Raspberry Pi 4; an
            object-detection model trained in Edge Impulse (project 1094555) localizes component-level defects;
            and the good/defective verdict drives a rack-and-pinion mechanism that routes each board into one of
            two bins. A 16×2 LCD and a locally hosted web dashboard expose the verdict, defect label, confidence
            and inference latency. The detector covers one good-board class and nine defect classes. Across 1,478
            logged inspection cycles, 97 were flagged defective; measured inference latency stayed between 401 and
            488 ms (mean 428 ms). A survey of 29 recent studies shows that about one third lack industrial or
            deployment validation, which motivates this integrated design. Accuracy claims beyond Edge Impulse
            Studio metrics are not made without a full board-level hold-out evaluation.
          </p>
        </article>

        <article className="report-card">
          <h3>02 · Team</h3>
          <div className="team-grid">
            {team.map((m) => (
              <div className="team-item" key={m.usn}>
                <b>{m.name}</b>
                <span>{m.usn}</span>
              </div>
            ))}
          </div>
          <p className="muted">Guide: Dr. Chethan K S, Assistant Professor, Dept. of ECE</p>
        </article>

        <article className="report-card">
          <h3>03 · Problem statement</h3>
          <p>
            Manual PCB inspection is slow, operator-dependent and easily misses small defects, while most AI
            studies stop at detection output. Industry needs a low-cost system that finds component-level defects
            on every board, reports the result clearly and automatically separates defective boards from good ones
            on the line.
          </p>
          <ul className="report-list">
            <li><b>Detection stops at output</b> — proposed: verdict drives conveyor pause and bin routing.</li>
            <li><b>Generic categories</b> — proposed: 1 good + 9 component-level defect classes.</li>
            <li><b>Heavy models</b> — proposed: compact int8 Edge Impulse model on Raspberry Pi 4.</li>
            <li><b>Little deployment evidence</b> — proposed: on-device log (1,478 cycles), history and analytics.</li>
          </ul>
        </article>

        <article className="report-card">
          <h3>04 · Objectives</h3>
          <ol className="report-list numbered">
            <li>Capture PCB images on a conveyor and run AI inference locally on a Raspberry Pi 4.</li>
            <li>Detect component-level defects (missing IC, pins, capacitor, inductor, potentiometer, heat sink, burned track, over-soldering).</li>
            <li>Classify every board as Good or Defective with a confidence-threshold decision rule.</li>
            <li>Control the conveyor: pause about 4–5 s for inspection, then resume (only while live detection is on).</li>
            <li>Segregate boards into two bins using a rack-and-pinion mechanism (move only when bin side must change).</li>
            <li>Show status on a 16×2 LCD and this web dashboard (live view, history, analytics).</li>
            <li>Evaluate on real boards, report model metrics and latency, and state limitations honestly.</li>
          </ol>
        </article>

        <article className="report-card">
          <h3>05 · Literature survey (29 studies, 2022–2026)</h3>
          <p>
            Detector research clusters around YOLO variants (attention, multi-scale, lightweight). Sorting papers
            link vision to bins but often use generic waste classes, not component-level PCB faults. Primary
            limitations recorded across 29 surveyed works:
          </p>
          <div className="simple-table">
            <div><span>Missing industrial / deployment validation</span><b>9 (31%)</b></div>
            <div><span>Computational cost or model complexity</span><b>6 (21%)</b></div>
            <div><span>Dataset scope, size or augmentation</span><b>5 (17%)</b></div>
            <div><span>Imaging / illumination, tiny defects, tuning, baseline accuracy, other</span><b>9 (31%)</b></div>
          </div>
          <p className="muted">
            69% are held back by missing deployment validation, compute cost or data coverage. Design response:
            compact detector on target hardware, actuator driven by the verdict, on-device logging.
          </p>
        </article>

        <article className="report-card">
          <h3>06 · Proposed system architecture</h3>
          <p>
            Boards ride the belt under a fixed overhead camera. The Raspberry Pi 4 captures frames (OpenCV),
            runs the Edge Impulse object detector (.eim via edge-impulse-linux), applies the decision rule, then
            simultaneously: pauses/resumes the belt motor (L293D), moves segregation only if the required bin side
            changes, updates the LCD, and writes the dashboard log.
          </p>
          <ul className="report-list">
            <li>Controller: Raspberry Pi 4 Model B (Raspberry Pi OS 64-bit)</li>
            <li>Imaging: USB / Pi camera on a bridge above the belt</li>
            <li>Conveyor: belt + 12 V DC gear motor through dual H-bridge (L293D / L298N-class)</li>
            <li>Routing: gear motor + rack-and-pinion → two-compartment bin</li>
            <li>Local display: 16×2 parallel LCD (BOARD pins D7=37 … RS=40, E=38)</li>
            <li>Software: Python FastAPI backend, React+Vite frontend, Edge Impulse Linux SDK</li>
          </ul>
        </article>

        <article className="report-card">
          <h3>07 · Dataset, classes and model</h3>
          <p>
            Trained in Edge Impulse Studio (project 1094555). About 1,637 labelled items; 13 label strings that
            collapse to 10 classes because of letter-case duplicates. YOLO-Pro small (pretrained), 100 training
            cycles, target Linux AARCH64 int8 for Raspberry Pi 4. Deployed runtime is the ~22 MB .eim model file
            (model.eim / mainmodel.eim).
          </p>
          <div className="simple-table">
            <div><span>pcb_good</span><b>Good</b></div>
            <div><span>IC_missing / Pins_Missing</span><b>Defective</b></div>
            <div><span>Capacitor_Missing / Inductor_Missing / Potentiometer_Missing</span><b>Defective</b></div>
            <div><span>Heat_Sink_Missing / Component_missing</span><b>Defective</b></div>
            <div><span>Over_Soldered / Track_burned</span><b>Defective</b></div>
          </div>
          <p>
            Verdict: DEFECTIVE if any defect class has confidence ≥ τ; otherwise GOOD. Live displays included
            detections as low as ~36%, so operating τ was no higher than that in the evaluated build.
          </p>
        </article>

        <article className="report-card">
          <h3>08 · Model performance (Edge Impulse Studio)</h3>
          <div className="metric-row">
            <div><strong>0.93</strong><span>Validation mAP@50</span></div>
            <div><strong>0.76</strong><span>Test mAP@50</span></div>
            <div><strong>0.78</strong><span>Test recall</span></div>
            <div><strong>428 ms</strong><span>Mean live latency on Pi 4</span></div>
          </div>
          <p className="muted">
            Int8 vs float32 (Studio estimates): lower latency and much smaller flash/RAM. Measured live latency
            from log entries: 401–488 ms (mean 428 ± 31 ms) ≈ 2.3 inferences/s. Gap between validation and test
            mAP indicates need for more board variety.
          </p>
        </article>

        <article className="report-card">
          <h3>09 · Hardware control behaviour</h3>
          <ul className="report-list">
            <li>Conveyor runs only while Live Detection is started; stops when live mode ends.</li>
            <li>On detection: pause conveyor ~5 s, show LCD message, segregation pulse ~3.8 s only if side must change, then resume.</li>
            <li>Repeated defect (or repeated good) leaves the slider idle on the current side.</li>
            <li>Cooldown after each board reduces double-triggering on the same PCB still in view.</li>
            <li>Optional PWM on L293D EN pins for reduced belt speed (CONV_SPEED env, e.g. 35–40%).</li>
          </ul>
        </article>

        <article className="report-card">
          <h3>10 · Software stack (this repository)</h3>
          <div className="simple-table">
            <div><span>fastapi, uvicorn, pydantic</span><b>REST API + ASGI server</b></div>
            <div><span>edge-impulse-linux</span><b>Load .eim and run object detection</b></div>
            <div><span>opencv-python-headless, numpy, Pillow</span><b>Camera capture and image IO</b></div>
            <div><span>RPi.GPIO, RPLCD</span><b>Motors (BOARD mode) and parallel LCD</b></div>
            <div><span>React + Vite + lucide-react</span><b>Operator dashboard (this UI)</b></div>
            <div><span>sqlite3</span><b>Inspection history persistence</b></div>
          </div>
        </article>

        <article className="report-card">
          <h3>11 · Results from on-device log</h3>
          <div className="metric-row">
            <div><strong>1,478</strong><span>Logged cycles</span></div>
            <div><strong>97</strong><span>Flagged defective (6.6%)</span></div>
            <div><strong>1,381</strong><span>Good / no detection</span></div>
            <div><strong>≈2.3/s</strong><span>Inference rate</span></div>
          </div>
          <p>
            Per-class detections observed in analytics (examples): Component_missing 40, Pins_Missing 27,
            Capacitor_Missing 19, Track_burned 11, Inductor_Missing 6, Heat_Sink_Missing 5, Potentiometer_Missing 3;
            pcb_good spellings merged ≈ 62. Counts are frame-level, not board-level—one physical board in view for
            several cycles can be counted more than once.
          </p>
        </article>

        <article className="report-card">
          <h3>12 · Advantages and applications</h3>
          <ul className="report-list">
            <li>Low cost: Raspberry Pi 4, no discrete GPU required for the prototype.</li>
            <li>Consistent inspection without operator fatigue; component-level labels on the dashboard.</li>
            <li>Closed loop: detect → pause → LCD/dashboard → segregate → resume.</li>
            <li>Applications: end-of-line checks, incoming QA, teaching labs, product-specific retraining in Edge Impulse.</li>
          </ul>
        </article>

        <article className="report-card">
          <h3>13 · Limitations</h3>
          <ul className="report-list">
            <li>Held-out test mAP@50 is 0.76; end-to-end segregation success rate not yet measured on a large set.</li>
            <li>Log counts are frame-level, not board-level.</li>
            <li>Only a few module-type board layouts were tested in the lab.</li>
            <li>Latency statistics rest on a limited number of consecutive log readings.</li>
            <li>Verdict is binary (good vs defective); severity grading is future work.</li>
            <li>Duplicate label spellings (pcb_good / PCB_Good) should be merged in Studio.</li>
          </ul>
        </article>

        <article className="report-card">
          <h3>14 · Future scope</h3>
          <ol className="report-list numbered">
            <li>Larger labelled hold-out evaluation: precision, recall, mAP, confusion matrix.</li>
            <li>Measure segregation success at several belt speeds.</li>
            <li>PCB-position sensor and fixed lighting for a repeatable trigger.</li>
            <li>Class-specific thresholds and a manual-review path for low-confidence boards.</li>
            <li>Count boards instead of frames; merge duplicate labels.</li>
            <li>Severity grading: pass / rework / reject; optional accelerator for higher throughput.</li>
          </ol>
        </article>

        <article className="report-card">
          <h3>15 · Conclusion</h3>
          <p>
            A working low-cost AI inspection and segregation prototype was built on a Raspberry Pi 4 with camera,
            conveyor, LCD and web dashboard. An Edge Impulse detector recognises 1 good and 9 defect classes at
            component level (validation mAP@50 0.93, test 0.76). Inference runs on the device at about 0.43 s per
            frame. The verdict pauses the belt, updates the LCD and dashboard, and routes the board into the Good
            or Defective bin. 1,478 cycles were logged on device. Next steps are a larger hold-out evaluation,
            sensor-based triggering and severity grading.
          </p>
        </article>

        <article className="report-card">
          <h3>16 · Key references</h3>
          <ul className="report-list refs">
            <li>J. Redmon et al., “You only look once…,” IEEE CVPR, 2016.</li>
            <li>S. Hymel et al., “Edge Impulse: An MLOps platform for tiny machine learning,” arXiv:2212.03332, 2022.</li>
            <li>W. Chen et al., “PCB defect detection method based on Transformer-YOLO,” IEEE Access, 2022.</li>
            <li>C. Mo et al., “SGT-YOLO: A lightweight method for PCB defect detection,” IEEE TIM, 2025.</li>
            <li>Edge Impulse Studio project 1094555 — PCBs Defects Detection and segregation.</li>
            <li>Full reference list (33 entries) in the IEEE conference paper of this project.</li>
          </ul>
        </article>
      </div>
    </section>
  );
}


createRoot(document.getElementById('root')).render(<App />);
