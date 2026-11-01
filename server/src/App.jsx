import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle, BookOpen, Copy, LayoutDashboard, Loader2, Mic, RefreshCw, Scale, ShieldCheck,
  Sparkles, Square, Table2, Tag, Upload, Volume2, X,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const MAX_BYTES = 12 * 1024 * 1024;

const LANGS = {
  Hindi: "hi-IN", English: "en-IN", Marathi: "mr-IN", Telugu: "te-IN", Bengali: "bn-IN",
};
const GROUPS = ["All", "Small Business", "Student", "Senior Citizen", "Woman Entrepreneur", "Worker"];
const DEFAULT_GOAL =
  "Check my eligibility across all loaded clauses, calculate my annual benefit, and prepare a voice explainer.";
const EXAMPLE_TEXT = [
  "CLAUSE 4A: PM Street Vendor Samman - Monthly grant of INR 1200 for Small Business vendors aged 18 to 60 with annual income up to INR 180000.",
  "CLAUSE 7B: Municipal Trade License Fee Waiver - Flat INR 500 monthly rebate for Small Business retailers with annual income up to INR 250000.",
  "CLAUSE 9C: Right to 15-Day Grievance Redressal - Citizens have the right to written resolution within 15 days (INR 0 financial grant, universal eligibility).",
].join("\n");
const SAMPLE_QUERIES = {
  Hindi: "नमस्ते, मेरी उम्र 28 साल है और वार्षिक आय 180000 रुपये है, मुझे सरकारी योजना के बारे में बताएं",
  English: "Hello, I am 28 years old with income 180000, tell me about this government scheme",
  Marathi: "नमस्कार, माझे वय 28 वर्षे आहे आणि उत्पन्न 180000 आहे, मला सरकारी योजनेबद्दल सांगा",
  Telugu: "నమస్కారం, నా వయస్సు 28 మరియు ఆదాయం 180000, ప్రభుత్వ పథకం గురించి చెప్పండి",
  Bengali: "নমস্কার, আমার বয়স 28 এবং আয় 180000 টাকা, সরকারি প্রকল্প সম্পর্কে বলুন",
};
const MIC_MSG =
  "Voice microphone recognition is unavailable or blocked in this browser. Use the 'Simulate Voice Query' button or type directly.";
const TTS_MSG = "Browser speech synthesis unavailable; read or copy the regional transcript below.";
const CAT_COLORS = ["#4b56d2", "#127a4a", "#d99a00", "#b4372f", "#7a4bd2", "#2b8fb5", "#8a8fa6"];

const inr = (n) =>
  "₹" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtDate = (d) =>
  d
    ? new Date(d + "T00:00:00Z").toLocaleDateString("en-US", {
        month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
      })
    : "Date unclear";

async function api(path, options) {
  let res;
  try {
    res = await fetch(`${API}${path}`, options);
  } catch {
    throw new Error(`Cannot reach the backend at ${API}. Is it running?`);
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON body */ }
  if (!res.ok) {
    let detail = data?.detail;
    if (Array.isArray(detail)) {
      detail = detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

const dotClass = (type) =>
  type === "tool" ? "green"
    : ["approval_required", "approved_simulation", "rejected"].includes(type) ? "amber"
    : type === "error" ? "red" : "blue";

export default function App() {
  const [health, setHealth] = useState(null);
  const [clauses, setClauses] = useState([]);
  const [source, setSource] = useState("Sample policy");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [notes, setNotes] = useState([]);
  const [busyExtract, setBusyExtract] = useState(false);
  const [busyAudit, setBusyAudit] = useState(false);
  const [busyDecision, setBusyDecision] = useState(false);
  const [profile, setProfile] = useState({
    age: "28", annual_income: "180000", target_group: "Small Business", language: "Hindi",
  });
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [session, setSession] = useState(null);
  const [recording, setRecording] = useState(null); // "policy" | "goal" | null
  const [speaking, setSpeaking] = useState(false);
  const [copied, setCopied] = useState(false);
  const recogRef = useRef(null);

  const stopListening = useCallback(() => {
    try { recogRef.current?.stop(); } catch { /* already stopped */ }
    recogRef.current = null;
    setRecording(null);
  }, []);

  const stopSpeaking = useCallback(() => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  // Cleared at the start of every load / extract / audit.
  const resetTransient = useCallback(() => {
    setError("");
    setNotice("");
    stopListening();
    stopSpeaking();
  }, [stopListening, stopSpeaking]);

  const loadSample = useCallback(async () => {
    resetTransient();
    try {
      const data = await api("/api/sample");
      setClauses(data.clauses);
      setSource("Sample policy");
      setNotes([]);
      setSession(null);
      const p = data.default_profile;
      setProfile({
        age: String(p.age), annual_income: String(p.annual_income),
        target_group: p.target_group, language: p.language,
      });
    } catch (e) {
      setError(e.message);
    }
  }, [resetTransient]);

  useEffect(() => {
    api("/api/health").then(setHealth).catch(() => setHealth({ status: "down", gemini_configured: false }));
    loadSample();
    return () => { window.speechSynthesis?.cancel(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- Dashboard calculations (deterministic, client-side) ----------
  const stats = useMemo(() => {
    const monetary = clauses.filter((c) => c.monthly_benefit > 0);
    return {
      count: clauses.length,
      schemes: new Set(clauses.map((c) => c.scheme_name)).size,
      annualPool: monetary.reduce((s, c) => s + c.monthly_benefit * 12, 0),
      grants: monetary
        .filter((c) => c.category === "Financial Grant")
        .reduce((s, c) => s + c.monthly_benefit, 0),
    };
  }, [clauses]);

  const chartData = useMemo(() => {
    const map = new Map();
    clauses.filter((c) => c.monthly_benefit > 0).forEach((c) => {
      map.set(c.scheme_name, (map.get(c.scheme_name) || 0) + c.monthly_benefit * 12);
    });
    return [...map.entries()]
      .map(([name, v]) => ({ name, annual_benefit: Math.round(v * 100) / 100 }))
      .sort((a, b) => b.annual_benefit - a.annual_benefit);
  }, [clauses]);

  const categories = useMemo(() => {
    const map = new Map();
    clauses.forEach((c) => map.set(c.category, (map.get(c.category) || 0) + 1));
    const list = [...map.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
      .slice(0, 6);
    const max = Math.max(1, ...list.map((c) => c.count));
    return list.map((c) => ({ ...c, width: Math.max(5, (c.count / max) * 100) }));
  }, [clauses]);

  const tableRows = useMemo(
    () =>
      [...clauses].sort((a, b) => {
        if (!a.effective_date && !b.effective_date) return 0;
        if (!a.effective_date) return 1;
        if (!b.effective_date) return -1;
        return b.effective_date.localeCompare(a.effective_date);
      }),
    [clauses]
  );

  // ---------- Voice input (Speech-to-Text) ----------
  const startListening = (target) => {
    if (recording === target) { stopListening(); return; }
    stopListening();
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { setNotice(MIC_MSG); return; }
    try {
      const rec = new SR();
      rec.lang = LANGS[profile.language];
      rec.interimResults = true;
      rec.continuous = false;
      const base = target === "policy" && text ? text.trimEnd() + " " : "";
      rec.onresult = (e) => {
        let t = "";
        for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
        if (target === "policy") setText(base + t); else setGoal(t);
      };
      rec.onerror = () => { setNotice(MIC_MSG); recogRef.current = null; setRecording(null); };
      rec.onend = () => setRecording((cur) => (cur === target ? null : cur));
      recogRef.current = rec;
      rec.start();
      setNotice("");
      setRecording(target);
    } catch {
      setNotice(MIC_MSG);
      setRecording(null);
    }
  };

  // ---------- Voice output (Text-to-Speech) ----------
  const speak = () => {
    const pa = session?.pending_action;
    if (!pa) return;
    if (!("speechSynthesis" in window)) { setNotice(TTS_MSG); return; }
    window.speechSynthesis.cancel();
    const checklist = (pa.draft.split("\n").filter((l) => /^\d+\./.test(l.trim())) || []).join(" ");
    const u = new SpeechSynthesisUtterance(`${pa.spoken_summary} ${checklist}`);
    u.lang = pa.tts_lang;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  };

  const copyScript = async () => {
    try {
      await navigator.clipboard.writeText(session.pending_action.draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setNotice("Could not copy automatically; select the script text and copy it manually.");
    }
  };

  // ---------- Actions ----------
  const onFile = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > MAX_BYTES) { setError("Please use a file smaller than 12 MB for this demo."); return; }
    setError("");
    setFile(f);
  };

  const extract = async () => {
    resetTransient();
    setBusyExtract(true);
    try {
      const form = new FormData();
      if (text.trim()) form.append("text", text.trim());
      if (file) form.append("file", file);
      const data = await api("/api/extract", { method: "POST", body: form });
      const extra = (data.validation_errors || []).map((v) => `Row ${v.row} dropped: ${v.error}`);
      setNotes([...(data.notes || []), ...extra]);
      if (!data.count) { setError("No valid policy clauses were extracted. Check the input and try again."); return; }
      setClauses(data.clauses);
      setSource("Your input");
      setSession(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyExtract(false);
    }
  };

  const runAudit = async () => {
    resetTransient();
    const age = Number(profile.age);
    const income = Number(profile.annual_income);
    if (!Number.isInteger(age) || age < 1 || age > 120) { setError("Age must be a whole number between 1 and 120."); return; }
    if (!Number.isFinite(income) || income < 0 || profile.annual_income === "") { setError("Annual income must be 0 or more."); return; }
    setBusyAudit(true);
    try {
      const data = await api("/api/audits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clauses,
          profile: { age, annual_income: income, target_group: profile.target_group, language: profile.language },
          goal,
        }),
      });
      setSession(data);
      // Sync UI with the effective profile (after any spoken overrides).
      setProfile({
        age: String(data.profile.age), annual_income: String(data.profile.annual_income),
        target_group: data.profile.target_group, language: data.profile.language,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyAudit(false);
    }
  };

  const decide = async (decision) => {
    setError("");
    stopSpeaking();
    setBusyDecision(true);
    try {
      setSession(await api(`/api/audits/${session.session_id}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyDecision(false);
    }
  };

  const go = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const pa = session?.pending_action;
  const awaiting = session?.status === "awaiting_approval";
  const lang = profile.language;
  const setP = (k) => (e) => setProfile((p) => ({ ...p, [k]: e.target.value }));

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Scale size={21} /></div>
          <div>
            <div className="brand-name">Lexora</div>
            <div className="brand-cap">POLICY &amp; VOICE EXPLAINER</div>
          </div>
        </div>
        <div>
          <div className="nav-label">CIVIC WORKSPACE</div>
          <nav className="nav">
            <button className="nav-item active" onClick={() => go("overview")}><LayoutDashboard size={17} /> Overview</button>
            <button className="nav-item" onClick={() => go("clauses")}>
              <Table2 size={17} /> Policy Clauses <span className="badge-count">{clauses.length}</span>
            </button>
            <button className="nav-item" onClick={() => go("voice")}><BookOpen size={17} /> Citizen Voice Explainer</button>
          </nav>
        </div>
        <div className="side-card">
          <strong><ShieldCheck size={16} /> Demo-safe civic mode</strong>
          Sample notifications are fictional. Voice explainers and checklists are simulated locally and never submitted to government portals.
          <div className="ver">HACKATHON BUILD · v1.0.0</div>
        </div>
      </aside>

      <main className="main" id="overview">
        <header className="topbar">
          <div>
            <div className="eyebrow">CIVIC INTELLIGENCE / MULTILINGUAL VOICE EXPLAINER</div>
            <h1>Policy &amp; rights overview</h1>
            <p className="subtitle">
              Speak or upload government notifications and hear plain regional-language voice explainers in Hindi, English, Marathi, Telugu, or Bengali.
            </p>
          </div>
          <div className="top-actions">
            <div className="status">
              <span className={`dot ${health?.gemini_configured ? "on" : ""}`} />
              {health?.gemini_configured ? "Gemini connected" : "Demo mode available"}
            </div>
            <button className="icon-btn" title="Reload sample scheme" aria-label="Reload sample scheme" onClick={loadSample}>
              <RefreshCw size={17} />
            </button>
            <div className="avatar">L</div>
          </div>
        </header>

        {error && (
          <div className="banner error" role="alert">
            <AlertCircle size={18} /><span>{error}</span>
            <button aria-label="Dismiss" onClick={() => setError("")}><X size={17} /></button>
          </div>
        )}
        {notice && (
          <div className="banner info" role="status">
            <AlertCircle size={18} /><span>{notice}</span>
            <button aria-label="Dismiss" onClick={() => setNotice("")}><X size={17} /></button>
          </div>
        )}

        <section className="metrics">
          <div className="card metric">
            <div className="label">Extracted clauses</div>
            <div className="value">{stats.count}</div>
            <div className="sub">{stats.schemes} distinct schemes</div>
          </div>
          <div className="card metric">
            <div className="label">Max annual benefit pool</div>
            <div className="value">{inr(stats.annualPool)}</div>
            <div className="sub">Across all monetary clauses</div>
          </div>
          <div className="card metric">
            <div className="label">Direct financial grants</div>
            <div className="value">{inr(stats.grants)}</div>
            <div className="sub">Monthly recurring grant pool</div>
          </div>
          <div className="card metric">
            <div className="label">Eligible schemes matched</div>
            <div className="value green">{session ? session.findings.length : "—"}</div>
            <div className="sub">{session ? "From your latest audit" : "Speak or run a citizen audit"}</div>
          </div>
        </section>

        <section className="row2">
          <div className="card">
            <div className="panel-head">
              <div>
                <h3>Annual benefit by scheme</h3>
                <p>Monetary schemes annualized (INR/year)</p>
              </div>
              <span className="pill">{source}</span>
            </div>
            {chartData.length === 0 ? (
              <div className="empty">Load monetary policy clauses to see annual benefit comparison.</div>
            ) : (
              <div style={{ width: "100%", height: 300 }}>
                <ResponsiveContainer>
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="4 4" stroke="#e2e5ee" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} tickFormatter={(v) => (v.length > 16 ? v.slice(0, 15) + "…" : v)} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => "₹" + v.toLocaleString("en-US")} width={70} />
                    <Tooltip formatter={(v) => [inr(v), "Annual benefit"]} />
                    <Bar dataKey="annual_benefit" fill="#4b56d2" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
          <div className="card">
            <div className="panel-head">
              <div>
                <h3>Clauses by category</h3>
                <p>Distribution across policy types</p>
              </div>
            </div>
            {categories.length === 0 ? (
              <div className="empty">Category breakdown appears after policy clauses are loaded.</div>
            ) : (
              categories.map((c, i) => (
                <div className="cat-row" key={c.name}>
                  <span className="cat-badge" style={{ background: CAT_COLORS[i % CAT_COLORS.length] }}><Tag size={14} /></span>
                  <span className="cat-name">{c.name}</span>
                  <span className="cat-count">{c.count}</span>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${c.width}%`, background: CAT_COLORS[i % CAT_COLORS.length] }} />
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="card">
          <div className="panel-head">
            <div>
              <div className="kicker">GENAI POLICY EXTRACTION &amp; VOICE INPUT</div>
              <h2>Ingest government notification or law</h2>
            </div>
            <span className="pill">01 Extract &amp; validate</span>
          </div>
          <div className="import-grid">
            <label className="drop">
              <input type="file" accept="image/*,.pdf,.csv,.txt" onChange={onFile} />
              <Upload size={26} />
              {file ? (
                <>
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024).toFixed(1)} KB</span>
                  <button type="button" className="link-btn" onClick={(e) => { e.preventDefault(); setFile(null); }}>Remove</button>
                </>
              ) : (
                <>
                  <strong>Choose a gazette notification, scheme PDF, or image</strong>
                  <span>PNG, JPG, PDF, CSV or TXT · max 12 MB</span>
                  <span className="link-btn">Browse files</span>
                </>
              )}
            </label>
            <div className="or">OR</div>
            <div>
              <div className="field-label">
                <span>Paste or speak policy notification text</span>
                <span className="field-tools">
                  {recording === "policy" && <span className="listening">Listening...</span>}
                  <button
                    type="button"
                    className={`btn small mic ${recording === "policy" ? "rec" : ""}`}
                    onClick={() => startListening("policy")}
                  >
                    <Mic size={15} /> Speak Policy Text ({lang})
                  </button>
                  <button type="button" className="link-btn" onClick={() => setText(EXAMPLE_TEXT)}>Use example</button>
                </span>
              </div>
              <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste raw gazette or circular lines here…" />
            </div>
          </div>
          <div className="import-foot">
            <p className="note">Structured output + schema validation. Unclear income/age thresholds stay null, never guessed.</p>
            <div className="btns">
              <button className="btn" onClick={loadSample}>Load sample scheme</button>
              <button className="btn primary" onClick={extract} disabled={busyExtract || (!text.trim() && !file)}>
                {busyExtract ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />} Extract policy clauses
              </button>
            </div>
          </div>
          {notes.length > 0 && (
            <div className="notes-box">
              <strong>Extraction notes</strong>
              <ul>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          )}
        </section>

        <section className="card" id="clauses">
          <div className="panel-head">
            <div>
              <h2>Policy Clauses</h2>
              <p>Validated, typed rules feeding the eligibility engine</p>
            </div>
            <span className="pill">{clauses.length} clauses</span>
          </div>
          {tableRows.length === 0 ? (
            <div className="empty">No policy clauses yet. Load the sample scheme or extract a notification above.</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CLAUSE ID &amp; SCHEME</th><th>EFFECTIVE DATE</th><th>CATEGORY</th>
                    <th>TARGET GROUP &amp; LIMITS</th><th>RAW CLAUSE</th><th className="num">MONTHLY BENEFIT</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((c) => (
                    <tr key={c.clause_id}>
                      <td><div className="scheme">{c.scheme_name}</div><div className="muted">{c.clause_id}</div></td>
                      <td>{fmtDate(c.effective_date)}</td>
                      <td><span className="chip">{c.category}</span></td>
                      <td>
                        <div>{c.target_group}</div>
                        <div className="muted">
                          {c.max_income_limit != null ? `Income ≤ ${inr(c.max_income_limit)}` : "No income cap"} ·{" "}
                          {c.min_age != null || c.max_age != null
                            ? `Age ${c.min_age ?? "any"}–${c.max_age ?? "any"}`
                            : "All ages"}
                        </div>
                      </td>
                      <td className="raw">{c.raw_clause || "—"}</td>
                      <td className="num">
                        {c.monthly_benefit > 0
                          ? <span className="benefit">{inr(c.monthly_benefit)}</span>
                          : <span className="nonmon">Non-monetary</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section id="voice">
          <div className="section-head">
            <div className="kicker">MULTILINGUAL VOICE AGENT (STT + TTS)</div>
            <h2>Speak your query &amp; run voice explainer</h2>
            <p>Speak in Hindi, English, Marathi, Telugu, or Bengali. The agent extracts your spoken details, verifies eligibility with deterministic Python tools, and speaks back your explainer.</p>
          </div>
          <div className="agent-grid">
            <div className="card">
              <div className="profile-grid">
                <label>Age
                  <input type="number" min="1" max="120" value={profile.age} onChange={setP("age")} />
                </label>
                <label>Annual Income (INR)
                  <input type="number" min="0" value={profile.annual_income} onChange={setP("annual_income")} />
                </label>
                <label>Citizen / Business Group
                  <select value={profile.target_group} onChange={setP("target_group")}>
                    {GROUPS.map((g) => <option key={g}>{g}</option>)}
                  </select>
                </label>
                <label>Voice &amp; Explainer Language
                  <select value={profile.language} onChange={setP("language")}>
                    {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{k} ({v})</option>)}
                  </select>
                </label>
              </div>
              <div className="field-label">
                <span>Speak or type your scheme question</span>
                <span className="field-tools">
                  {recording === "goal" && <span className="listening">Listening...</span>}
                  <button type="button" className={`btn small mic ${recording === "goal" ? "rec" : ""}`} onClick={() => startListening("goal")}>
                    <Mic size={15} /> Speak Query ({lang})
                  </button>
                  <button type="button" className="btn small" onClick={() => setGoal(SAMPLE_QUERIES[lang])}>Simulate Voice Query</button>
                </span>
              </div>
              <textarea rows={4} value={goal} onChange={(e) => setGoal(e.target.value)} />
              <p className="note" style={{ margin: "8px 0 14px" }}>
                Eligibility math runs deterministically. Voice scripts and action checklists require your review. Nothing is submitted externally.
              </p>
              <button className="btn primary full" onClick={runAudit} disabled={busyAudit || clauses.length === 0}>
                {busyAudit && <Loader2 size={16} className="spin" />} Run eligibility &amp; voice explainer
              </button>
            </div>

            <div className="card">
              <div className="panel-head">
                <div>
                  <h3>Agent trace</h3>
                  <p>Voice parsing, tools, observations and decisions</p>
                </div>
                {session && (
                  <span className={`pill ${session.status === "failed" ? "red" : session.status === "awaiting_approval" ? "amber" : session.status === "done" ? "green" : ""}`}>
                    {session.status.replace("_", " ")}
                  </span>
                )}
              </div>
              {!session ? (
                <div className="empty">The agent trace appears here after you run an audit.</div>
              ) : (
                <>
                  <div className="summary-box">{session.summary || "Audit in progress…"}</div>
                  <ol className="timeline">
                    {session.audit_log.map((e, i) => (
                      <li className="t-item" key={i}>
                        <span className={`t-dot ${dotClass(e.type)}`} />
                        <div className="t-msg">{e.message}</div>
                        <div className="t-meta">
                          {e.type} · {new Date(e.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </div>
                        {e.type === "plan" && (
                          <code className="t-code">{e.details.tool}({JSON.stringify(e.details.arguments || {})})</code>
                        )}
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {session && session.findings.length > 0 && (
                <div className="findings">
                  {session.findings.map((f) => (
                    <div className="finding" key={f.clause_id}>
                      <div className="head">
                        <span className="pill green">Eligible scheme</span>
                        <span className="muted">{f.target_group}</span>
                      </div>
                      <h4>{f.scheme_name}</h4>
                      <div className="money">{inr(f.monthly_benefit)}/month → {inr(f.annual_benefit)}/year</div>
                      <div className="foot"><span>Clause {f.clause_id}</span><span>{f.reason}</span></div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {pa && (
            <div className="card approval" style={{ marginTop: 16 }}>
              <div className="panel-head" style={{ marginBottom: 0 }}>
                <div>
                  <div className="kicker">HUMAN-IN-THE-LOOP &amp; REGIONAL VOICEOVER</div>
                  <h2 style={{ margin: "4px 0" }}>
                    {pa.approved === undefined ? "Voice explainer ready for review"
                      : pa.approved ? "Explainer approved (simulation)" : "Explainer pack rejected"}
                  </h2>
                  <p className="muted" style={{ margin: 0 }}>{pa.language} ({pa.tts_lang}) · {pa.scheme_count} matched scheme(s)</p>
                </div>
                <span className={`pill ${awaiting ? "amber" : "green"}`}>{awaiting ? "Awaiting review" : "Decision recorded"}</span>
              </div>
              <div className="pills3">
                <div className="pill-metric"><div className="l">Matched schemes</div><div className="v">{pa.scheme_count}</div></div>
                <div className="pill-metric"><div className="l">Combined monthly benefit</div><div className="v">{inr(pa.total_monthly)}</div></div>
                <div className="pill-metric"><div className="l">Annual INR impact</div><div className="v">{inr(pa.total_annual)}</div></div>
              </div>
              <div className="audio-bar">
                <button className="btn primary" onClick={speak}><Volume2 size={16} /> Listen to Voice Explainer ({pa.language})</button>
                <button className="btn" onClick={stopSpeaking}><Square size={14} /> Stop Audio</button>
                <button className="btn" onClick={copyScript}><Copy size={15} /> {copied ? "Copied" : "Copy Script"}</button>
                {speaking && <span className="pill amber">Speaking in {pa.language}...</span>}
              </div>
              <div>
                <div className="draft-label">
                  <span>REGIONAL VOICE EXPLAINER &amp; ACTION CHECKLIST</span>
                  <span className="pill amber">LOCAL SIMULATION ONLY</span>
                </div>
                <pre className="draft">{pa.draft}</pre>
              </div>
              {awaiting && (
                <div className="approval-foot">
                  <button className="btn danger" disabled={busyDecision} onClick={() => decide("reject")}>Reject</button>
                  <button className="btn primary" disabled={busyDecision} onClick={() => decide("approve")}>
                    {busyDecision && <Loader2 size={16} className="spin" />} Approve explainer pack
                  </button>
                </div>
              )}
            </div>
          )}
        </section>

        <footer className="footer">
          <strong>LEXORA · MULTILINGUAL POLICY, RIGHTS &amp; SCHEME EXPLAINER</strong>
          <span>Built for civic awareness · Supports Hindi, English, Marathi, Telugu &amp; Bengali · Not official legal counsel</span>
        </footer>
      </main>
    </div>
  );
}
