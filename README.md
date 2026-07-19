<div align="center">

<img src="https://setusync.space/favicons/logo1.webp" alt="Setu Logo" width="90"/>

# सेतु · SetuSync

**Real-time collaboration, secure file sharing & instant rooms — all in your browser.**

[![Live](https://img.shields.io/badge/🌐_Live-setusync.space-6C7CF0?style=for-the-badge)](https://setusync.space)
[![Backend](https://img.shields.io/badge/FastAPI-Python_3.11-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-Vanilla_HTML%2FJS-F2A93B?style=for-the-badge&logo=html5)](https://setusync.space)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker)](./setu_backend/Dockerfile)
[![License](https://img.shields.io/badge/License-MIT-34D399?style=for-the-badge)](./setu_backend/LICENSE)

</div>

---

## ✨ What is Setu?

**Setu** (सेतु — meaning *bridge* in Sanskrit) is a browser-based real-time collaboration platform.  
No downloads. No installs. Just create a room, share a link, and start working together.

> 💬 Chat · 📁 Share Files · 🎨 Draw Together · 🔗 Instant Rooms · 🔐 End-to-End Encrypted

---

## 🚀 Features at a Glance

| Feature | Description |
|---|---|
| 💬 **Real-Time Chat** | Reply, edit & unsend messages. Right-click / long-press context menus |
| 📁 **File & Folder Sharing** | Drag & drop, peer-to-peer, send to everyone or specific users |
| 🎨 **Collaborative Whiteboard** | Multi-user Excalidraw canvas synced across the room in real time |
| 🔗 **Instant Rooms** | Join via QR code, short code, or shareable link in seconds |
| 📱 **QR File Transfer** | Generate a QR for any file — one-time download, auto-delete after 7 minutes |
| 🔒 **Password Protection** | Password-lock your uploads with secure ticket-based access |
| 👥 **Member Management** | Live member list, select specific recipients, edit your nickname |
| ⚡ **Auto-Reconnect** | WebSocket reconnect with saved room state |
| 🌗 **Dark & Light Mode** | One-click theme toggle with smooth transitions |
| 📱 **Mobile Friendly** | Touch-optimized, adaptive sidebar drawer, PWA installable |

---

## 🏗️ Architecture

```
bridge/
├── setu-frontend/          # Static frontend (Cloudflare Pages)
│   ├── index.html          # Landing page
│   ├── setu.html           # Main collaboration app
│   ├── feature.html        # Feature showcase
│   ├── auth.html           # Login / Signup
│   ├── auth.js             # Auth flow (JWT + Appwrite)
│   ├── main.js             # App logic (WebSocket, file sharing, chat)
│   └── stylus.css          # Global design system
│
└── setu_backend/           # FastAPI backend (Docker / Render)
    ├── main.py             # App entrypoint, upload/download API
    ├── setu.py             # Room engine (WebSocket signaling)
    ├── auth_routes.py      # Authentication endpoints
    ├── auth_appwrite.py    # Appwrite integration (accounts, sessions)
    ├── crypto_utils.py     # AES chunked encryption / decryption
    ├── tg_client.py        # Telegram storage backend (Pyrogram)
    ├── db.py               # SQLAlchemy models & database
    ├── contact_api.py      # Contact form endpoint
    ├── whiteboard/         # Excalidraw sync server (Node.js)
    └── Dockerfile          # Production container config
```

---

## 🛠️ Tech Stack

### Frontend
- **Vanilla HTML / CSS / JavaScript** — zero framework overhead
- **Bootstrap 5** — responsive grid & utilities
- **Font Awesome 6** — icons
- **Excalidraw** — collaborative whiteboard
- **Cloudflare Pages** — hosting with edge CDN

### Backend
- **FastAPI** (Python 3.11) — async REST + WebSocket API
- **SQLAlchemy** — ORM for SQLite / PostgreSQL
- **Appwrite** — user auth & session management
- **Pyrogram** — Telegram as encrypted file storage backend
- **Gunicorn + Uvicorn** — production WSGI/ASGI server
- **Node.js** — Excalidraw sync server subprocess
- **Docker** — containerized deployment on Render

---

## ⚡ Quick Start (Local Dev)

### Backend

```bash
# 1. Clone the repo
git clone https://github.com/your-username/setu-sync.git
cd setu-sync/setu_backend

# 2. Create & activate virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.template .env
# Fill in your Appwrite, Telegram, and DB credentials in .env

# 5. Run the dev server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd setu-frontend

# Option 1: Serve locally (Python)
python -m http.server 3000

# Option 2: Deploy to Cloudflare Pages (uses wrangler.jsonc config)
npx wrangler pages dev .
```

> Backend: `http://localhost:8000`  
> Frontend: `http://localhost:3000`

---

## 🔧 Environment Variables

Create a `.env` file in `setu_backend/` based on `.env.template`:

```env
# Appwrite (Auth)
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_api_key

# Telegram (File Storage)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_STRING=your_session_string
TELEGRAM_CHAT_ID=your_storage_chat_id

# CORS
ALLOWED_ORIGINS=https://setusync.space,http://localhost:3000

# Database
DATABASE_URL=sqlite:///./setu.db
```

---

## 🐳 Docker Deployment

```bash
cd setu_backend

# Build the image
docker build -t setu-backend .

# Run the container
docker run -p 8000:8000 --env-file .env setu-backend
```

The `Dockerfile` includes:
- Python 3.11 slim base
- Node.js 18 (for the Excalidraw sync server)
- Gunicorn + Uvicorn workers
- Automatic whiteboard `npm install` on build

---

## 🔐 Security

- **Chunked AES Encryption** — files are encrypted before uploading to Telegram storage
- **JWT Sessions** — HttpOnly cookies with Appwrite-backed session tokens
- **Password-Protected Uploads** — optional password lock with bcrypt hashing
- **One-Time Downloads** — files auto-delete after a single access
- **Rate Limiting** — in-memory token bucket on room creation (10 req/min)
- **CORS** — strict origin allowlist via environment variable
- **Path Traversal Prevention** — safe `arcname` sanitisation on all zip uploads
- **Auto-Cleanup Worker** — background task deletes expired shares & orphaned rooms every 60 seconds

---

## 🌐 Live App

| Link | Description |
|---|---|
| [setusync.space](https://setusync.space) | 🏠 Home / Landing page |
| [setusync.space/setu.html](https://setusync.space/setu.html) | 🚀 Launch the collaboration app |
| [setusync.space/feature.html](https://setusync.space/feature.html) | ✨ Feature showcase |
| [setusync.space/auth.html](https://setusync.space/auth.html) | 🔐 Login / Sign up |

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](./setu_backend/LICENSE) for details.

---

<div align="center">

Made with ❤️ by **Aham**

[🌐 Website](https://setusync.space) · [✉️ Contact](https://setusync.space/setu_contact.html) · [📋 Privacy Policy](https://setusync.space/privacy_policy.html)

</div>
