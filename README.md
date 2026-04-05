<div align="center">

```
  ██╗     ██╗   ██╗██╗  ██╗███████╗
  ██║     ██║   ██║██║ ██╔╝██╔════╝
  ██║     ██║   ██║█████╔╝ █████╗  
  ██║     ██║   ██║██╔═██╗ ██╔══╝  
  ███████╗╚██████╔╝██║  ██╗███████╗
  ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝
```

**Attention Guard · Memory Desk**

*Your screen's best friend.*

[![Built with Electron](https://img.shields.io/badge/Electron-React-4a7fff?style=flat-square&logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Claude API](https://img.shields.io/badge/Claude-API-f5a442?style=flat-square)](https://anthropic.com)
[![ElevenLabs](https://img.shields.io/badge/ElevenLabs-Voice-4a7fff?style=flat-square)](https://elevenlabs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-50c878?style=flat-square)](LICENSE)
[![Hackathon 2025](https://img.shields.io/badge/Hackathon-2025-a78bfa?style=flat-square)]()

</div>

---

## What is Luke?

Luke is an AI-powered desktop companion that **lives on your screen**. He watches your cognitive load in real time, catches you before you make a mistake you'll regret, and speaks your language — without ever getting in the way.

He's not an app you open. He's a presence. Always there. Never annoying.

Built specifically for **students**, **people with ADHD and dyslexia**, and **mental health counselors** — the three groups that mainstream software has always left behind.

> 75% of high school students are stressed all the time. 1 in 3 college students has anxiety or depression. 366 million adults globally have ADHD and lose 22 working days per year to unsupported brains. Luke is for them.

---

## Demo

> 📺 *Demo video coming soon*

**The moment that matters:** Type an angry message anywhere on your screen. Wait 3 seconds. Luke intercepts it before you send it and guides you through a 60-second reset.

---

## Features

### Phase 1 — Live Now
| Feature | What it does |
|---|---|
| **Animated Desktop Widget** | Luke lives in the corner of your screen. He blinks, breathes, and reacts. Draggable. Always on top. |
| **Live Cognitive Load Score** | 0–100 score updated every 10 seconds from facial emotion, open windows, switch count, and break history |
| **Hey Luke — Voice System** | Wake word triggers Whisper → Claude → ElevenLabs. Full conversational AI, eyes-free |
| **Chat Coach** | Reads clipboard every 3 seconds. Detects angry tone. Intercepts before you send. Guides a breathing reset. |

### Phase 2 — In Progress
| Feature | What it does |
|---|---|
| **Facial Emotion Detection** | face-api.js reads your webcam locally — 7 emotions, every 5 seconds. Zero video uploaded. |
| **Desktop Clarity Mode** | Tracks inactive apps. Auto-minimizes what you haven't touched in 10+ minutes. |
| **Study Visualizer** | "Hey Luke, visualize the Krebs cycle." Claude returns a clean SVG diagram instantly. |
| **Smart Reminders** | Context-aware nudges that adapt to your current stress level |

### Phase 3 — Roadmap
| Feature | What it does |
|---|---|
| **Micro Journal** | One word every evening at 7pm. After 30 days — a full mood calendar. |
| **Weekly Behavioral Report** | Stress trends, focus hours, emotional patterns. PDF export for counselors. |
| **Vent Mode** | "Hey Luke, I need to vent." Luke listens. Responds warmly. Stored locally only, never transmitted. |
| **Focus Shield** | Blocks interruptions for a set time. Full debrief after. |
| **Distraction Report** | At 6pm: "YouTube — 9 visits, 31 minutes." No blocking. Just the truth. |
| **ADHD Mode** | Audio-only, larger text, slower speech, auto Pomodoro. Built for neurodivergent users. |
| **Counselor Dashboard** | With consent, shares behavioral summaries with a therapist. Patterns only, never message content. |

---

## Tech Stack

```
Desktop Shell    →  Electron + React + Vite
Animations       →  Framer Motion
State            →  Zustand
Storage          →  SQLite via better-sqlite3 (local only)
Styling          →  Tailwind CSS

AI Brain         →  Anthropic Claude API (claude-sonnet-4-20250514)
Voice Output     →  ElevenLabs (eleven_turbo_v2)
Voice Input      →  OpenAI Whisper API
Emotion Vision   →  face-api.js (TinyFaceDetector — runs in-browser)
Tone Analysis    →  Sentiment.js
Calendar         →  Google Calendar API
```

---

## Privacy First

Luke is built on a simple promise: **your data never leaves your machine.**

- Face video is processed locally via face-api.js — nothing is uploaded
- Voice commands are transcribed and discarded — not stored
- All behavioral data (stress logs, vent entries, clipboard history) lives in a local SQLite database only
- Luke works fully offline after initial API key setup
- The counselor report feature shares patterns only — never message content, never vent transcripts

---

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- API keys for: Anthropic, ElevenLabs, OpenAI (for Whisper)

### Installation

```bash
# Clone the repo
git clone https://github.com/your-team/luke.git
cd luke

# Install dependencies
npm install

# Set up environment variables
cp .env.example .env
# Fill in your API keys (see Environment Variables below)

# Run in development
npm run dev

# Build for production
npm run build
```

### Environment Variables

Create a `.env` file in the root with:

```env
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your_key_here
GOOGLE_CLIENT_SECRET=your_key_here
```

---

## Project Structure

```
luke/
├── electron/
│   ├── main.js              # Electron main process
│   ├── preload.js           # Context bridge
│   └── windowManager.js     # Always-on-top window logic
├── src/
│   ├── components/
│   │   ├── LukeFace.jsx     # Animated SVG character
│   │   ├── StressRing.jsx   # Cognitive load ring
│   │   ├── ChatCoach.jsx    # Angry message interceptor
│   │   ├── VoiceListener.jsx# Wake word + Whisper
│   │   └── SidePanel.jsx    # Expanded Luke panel
│   ├── hooks/
│   │   ├── useStressScore.js
│   │   ├── useClipboard.js
│   │   ├── useVoice.js
│   │   └── useEmotion.js
│   ├── services/
│   │   ├── elevenlabs.js
│   │   ├── whisper.js
│   │   ├── claude.js
│   │   ├── sentiment.js
│   │   └── faceDetection.js
│   ├── store/
│   │   └── lukeStore.js     # Zustand global state
│   ├── db/
│   │   └── database.js      # SQLite local storage
│   └── App.jsx
├── .env.example
├── package.json
└── vite.config.js
```

---

## Luke's System Prompt

Every Claude API call uses this context-aware system prompt:

```
You are Luke, a warm emotionally intelligent desktop companion.
You help students, people with ADHD and dyslexia, and mental health counselors.

Rules:
- Max 50 words per response unless the user asks for more
- Short sentences only — never bullet points in spoken responses
- Always acknowledge how the user is feeling before giving information
- Never moralize or lecture
- Gentle humor when the user seems okay

Context injected with every message:
- stress_score: [0-100]
- dominant_emotion: [happy/sad/angry/fearful/neutral]
- time_of_day: [morning/afternoon/evening/night]
- open_windows: [number]
- last_break: [X minutes ago]
```

---

## Who It's For

**Students** — 47 tabs, 0 focus, exam in 6 hours. Luke watches their stress, visualizes study concepts on voice command, and actually tells them to take a break.

**ADHD + Dyslexia** — 366 million adults with ADHD. 1 in 10 with dyslexia. Luke's audio-only, low-clutter, voice-first design is built for how their brains actually work — not retrofitted.

**Mental Health Counselors** — Walk into every session with a behavioral summary: stress trends, emotional peaks, focus data. Without asking the client to do a single extra thing.

---

## The Numbers

| Stat | Source |
|---|---|
| 75% of high school students feel academic stress *all the time* | EssayPro, 2025 |
| 1 in 3 college students has anxiety or depression | ACHA, 2025 |
| 37% of people stop therapy due to cost or access | US Therapy Access Survey, 2022 |
| 366M adults globally have ADHD | Global ADHD Meta-Analysis, 2024 |
| 22 working days lost per year by adults with untreated ADHD | ADDA Workplace Studies, 2025 |
| $122.8B annual US cost of adult ADHD | Journal of Managed Care, 2025 |

---

## Team

**Luke Out For Us** — Built at Hackathon 2025

| Name | Role |
|---|---|
| Aryan | Builder |
| Arshia | Builder |
| Divij | Builder |
| Vraj | Builder |

---

## Contributing

Luke is a hackathon project — but if you want to build on it, go for it.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'add: your feature'`
4. Push and open a PR

---

## License

MIT — do whatever you want, just don't make something that hurts people.

---

<div align="center">

*Most tools optimize for output.*
*Luke optimizes for the human behind the output.*

**Built with care by Luke Out For Us · 2025**

</div>
