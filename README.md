# Lexora: Multilingual Policy, Rights & Scheme Explainer

A hackathon-ready full-stack demo that turns dense government notifications into structured policy clauses, checks citizen eligibility with deterministic tools, and speaks the result back in **Hindi, English, Marathi, Telugu or Bengali**.

> **Informational civic demo, not official legal counsel.** Sample schemes are fictional. Nothing is ever submitted to a government portal; "Approve" is a local simulation (`dispatched` is always `false`).
> **Privacy:** do **not** upload personal identity documents (Aadhaar, PAN, etc.). Use public or fictional notifications only. Audio is handled by the browser and never stored by the backend; sessions live in memory and vanish on restart.

## Project structure

```text
lexora-policy-explainer/
├── backend/
│   ├── app/
│   │   ├── ai_service.py   # AI boundary: STUB (hand-code the Gemini calls here)
│   │   ├── main.py         # FastAPI routes, bounded agent loop, in-memory sessions
│   │   ├── models.py       # Pydantic schemas
│   │   ├── sample_data.py  # 8 fictional INR policy clauses + default profile
│   │   └── tools.py        # Deterministic eligibility, voice-query parser, explainer
│   ├── tests/test_tools.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/               # React 18 + Vite 6 + Recharts + lucide-react
│   └── src/App.jsx  main.jsx  styles.css
└── README.md
```

## Prerequisites

- Python 3.11+ (3.12 recommended)
- Node 20+
- A Chromium-based browser (Chrome/Edge) for microphone speech recognition. Firefox lacks `SpeechRecognition`; use the **Simulate Voice Query** button there.

## Run locally

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1   (cmd: .venv\Scripts\activate.bat)
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

**Frontend** (new terminal)

```bash
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

Optional: set `VITE_API_URL` (default `http://localhost:8000`) when the backend is elsewhere.

## Configuration (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | `replace_me` | Placeholder counts as "not configured". Never commit real keys. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Used by your hand-coded integration |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS; comma-separated list allowed |

## Tests

```bash
cd backend
python -m pytest        # or: pytest
cd ../frontend && npm run build
```

## Demo mode vs. AI mode

Without an API key everything works except **extraction**, which returns a clear 503 "Gemini is not configured" error. The sample data, dashboard, voice input/output and the full agent audit run on a deterministic offline planner.

**Manual AI integration:** only `backend/app/ai_service.py` needs editing. Search for `TODO(manual)`:
1. `_client()`: create `google.genai.Client(api_key=key)`.
2. `extract_policy()`: call Gemini with `response_schema=PolicyDocument`, `temperature=0`, using `SYSTEM_EXTRACTION_PROMPT`.
3. `choose_next_step()`: optional LLM planner returning `AgentDecision`.

`main.py` treats all AI output as untrusted: every clause is re-validated, tool names are checked against the allowlist, and tool arguments are re-grounded in stored findings. Note that `/api/health` reports `gemini_configured: true` as soon as a key is present, even before you finish the integration.

## 6-step hackathon voice demo

1. Open the app. The sample scheme loads automatically (8 clauses, max annual pool ₹98,400.00).
2. Point out the chart and the category list, then the table with raw source lines.
3. In **Citizen Voice Explainer**, pick *Hindi* and click **Simulate Voice Query** (or use **Speak Query** with a mic).
4. Click **Run eligibility & voice explainer**. Show the trace (`started → plan → tool … → approval_required`) and the 3 matched schemes (₹4,200/month, ₹50,400/year).
5. Click **Listen to Voice Explainer (Hindi)** and hear the native-language voiceover. Switch language to try the others.
6. Click **Approve explainer pack** and note "Explainer approved (simulation)"; nothing was sent anywhere. Bonus: type *"My age is 20, income 100000, I am a student, explain in Marathi"* to see spoken overrides.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `{"status":"ok","gemini_configured":bool}` |
| GET | `/api/sample` | Fictional clauses + default profile |
| POST | `/api/extract` | Multipart `text` and/or `file` → validated clauses (400/413/503/502 on errors) |
| POST | `/api/audits` | Run the bounded (max 6 steps) eligibility & explainer audit |
| GET | `/api/audits/{id}` | Read a session |
| POST | `/api/audits/{id}/approval` | `{"decision":"approve"\|"reject","reason":"…"}` (404 unknown, 409 nothing pending) |

## Deploy on Render

*Backend (Web Service):* root `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `GEMINI_API_KEY`, `GEMINI_MODEL`, and `FRONTEND_ORIGIN` (your frontend URL).
*Frontend (Static Site):* root `frontend`, build `npm install && npm run build`, publish `dist`. Set `VITE_API_URL` to the backend URL.

## Documented assumptions

- The spec's `generate_voice_explainer` draft template was cut off after checklist item 3; I added item 4 (confirm final terms; informational, not legal advice).
- If a query matches several group keywords, the first in this order wins: Student, Senior Citizen, Woman Entrepreneur, Worker, Small Business.
- Comma-grouped numbers in spoken queries ("1,80,000") are normalised before the age/income regexes run.
- Speech synthesis reads the regional summary followed by the (English) checklist items.
- "Direct financial grants" is a **monthly** sum (₹6,000.00), per the acceptance criteria.

## Known limitations

- Single user, no auth, no database; sessions are lost on restart.
- Browser speech quality depends on installed OS/browser voices; Telugu/Bengali/Marathi voices may need to be installed.
- Extraction needs the manual Gemini integration.

## Troubleshooting

- **"Cannot reach the backend"**: start uvicorn on port 8000 and check `FRONTEND_ORIGIN`/`VITE_API_URL`.
- **Mic does nothing / banner appears**: use Chrome/Edge over `localhost` or HTTPS and allow microphone access; otherwise use *Simulate Voice Query*.
- **No audio / silent voiceover**: install a voice for the selected language in your OS, or use *Copy Script*.
- **`pytest` can't import `app`**: run it from `backend/` (the tests also add the path themselves).
- **PowerShell blocks venv activation**: `Set-ExecutionPolicy -Scope Process RemoteSigned`.
