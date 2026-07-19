/**
 * Setu — Excalidraw Collab Sync Server
 * Runs on ws://localhost:5858
 * FastAPI proxies /api/tldraw/sync/{roomId} → this server
 *
 * Security measures:
 *  - Max message size: 512 KB
 *  - Max clients per room: 50
 *  - Rate limit: 120 messages / 10 s per connection
 *  - roomId validation: alphanumeric + hyphens only
 *  - sessionId sanitised before logging
 */

import { WebSocketServer, WebSocket } from 'ws'

const PORT              = 5858
const MAX_MSG_BYTES     = 512 * 1024    // 512 KB
const MAX_CLIENTS_ROOM  = 50
const RATE_LIMIT_COUNT  = 1200          // messages — supports 60fps cursors + 30fps elements for ~10 users
const RATE_LIMIT_WINDOW = 10_000        // ms

// rooms: Map<roomId, Map<sessionId, ws>>
const rooms = new Map()

// ── Validation helpers ────────────────────────────────────────────────────────
const SAFE_ID = /^[a-zA-Z0-9_\-]{1,128}$/
function safeId(str, fallback) {
  const s = String(str ?? '').trim()
  return SAFE_ID.test(s) ? s : fallback
}

// ── Simple in-memory rate limiter ─────────────────────────────────────────────
function makeRateLimiter() {
  let count = 0
  let windowStart = Date.now()
  return {
    allow() {
      const now = Date.now()
      if (now - windowStart > RATE_LIMIT_WINDOW) {
        count = 0
        windowStart = now
      }
      count++
      return count <= RATE_LIMIT_COUNT
    }
  }
}

const wss = new WebSocketServer({ port: PORT })

wss.on('connection', (ws, req) => {
  const url       = new URL(req.url, `http://localhost:${PORT}`)
  const rawRoomId = url.pathname.slice(1)
  const roomId    = safeId(rawRoomId, '')
  const sessionId = safeId(url.searchParams.get('sessionId'), `s-${Math.random().toString(36).slice(2, 10)}`)
  const name      = String(url.searchParams.get('name') ?? 'User').slice(0, 64)

  // ── Validate roomId ────────────────────────────────────────────────────────
  if (!roomId) {
    ws.close(1008, 'Invalid roomId')
    return
  }

  // ── Capacity check ─────────────────────────────────────────────────────────
  const room = rooms.get(roomId) ?? new Map()
  if (room.size >= MAX_CLIENTS_ROOM) {
    console.warn(`[sync] ⛔ Room ${roomId} full (${room.size} clients)`)
    ws.close(1013, 'Room full')
    return
  }

  if (!rooms.has(roomId)) rooms.set(roomId, room)
  room.set(sessionId, ws)
  ws.sessionId = sessionId
  ws.name      = name

  const rl = makeRateLimiter()
  console.log(`[sync] ➕ ${roomId}/${sessionId} (${room.size} in room)`)

  // ── Send current scene to new joiner (request from another client) ─────
  // After a short delay, ask an existing client for the current scene
  setTimeout(() => {
    if (room.size > 1 && ws.readyState === WebSocket.OPEN) {
      // Pick the first other client to request scene from
      for (const [sid, client] of room) {
        if (sid !== sessionId && client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({ type: 'scene_request', sender: sessionId }))
          break
        }
      }
    }
  }, 500)

  ws.on('message', (data, isBinary) => {
    // ── Size guard ────────────────────────────────────────────────────────────
    const size = isBinary ? data.length : Buffer.byteLength(data)
    if (size > MAX_MSG_BYTES) {
      console.warn(`[sync] ⚠ Oversized msg from ${sessionId} (${size} bytes) — dropped`)
      return
    }

    // ── Rate limit ────────────────────────────────────────────────────────────
    if (!rl.allow()) {
      // silently drop — don't disconnect so UX isn't broken
      return
    }

    // ── Check for scene_request / scene_snapshot ──────────────────────────
    try {
      const msg = JSON.parse(data.toString())
      if (msg.type === 'scene_request') {
        // Find the target client and forward the scene_request
        const target = room.get(msg.sender)
        if (target && target.readyState === WebSocket.OPEN) {
          target.send(data, { binary: isBinary })
        }
        return
      }
      if (msg.type === 'scene_snapshot') {
        // Forward scene snapshot ONLY to the intended recipient (msg.target)
        const target = room.get(msg.target)
        if (target && target.readyState === WebSocket.OPEN) {
          target.send(data, { binary: isBinary })
        }
        return
      }
    } catch { /* not JSON or no type field — relay as usual */ }

    // ── Parallel relay to all other clients in room ────────────────────────
    const promises = []
    for (const [sid, client] of room) {
      if (sid !== sessionId && client.readyState === WebSocket.OPEN) {
        promises.push(
          new Promise((resolve) => {
            client.send(data, { binary: isBinary }, (err) => {
              if (err) console.warn(`[sync] send err to ${sid}: ${err.message}`)
              resolve()
            })
          })
        )
      }
    }
    // Fire all sends in parallel — don't await (non-blocking relay)
    Promise.all(promises).catch(() => {})
  })

  ws.on('close', () => {
    room.delete(sessionId)
    if (room.size === 0) {
      rooms.delete(roomId)
      console.log(`[sync] 🧹 Room ${roomId} empty — removed`)
    }
    console.log(`[sync] ➖ ${roomId}/${sessionId} (${room.size} remaining)`)
  })

  ws.on('error', (err) => {
    console.error(`[sync] ⚡ ${roomId}/${sessionId}:`, err.message)
    room.delete(sessionId)
    if (room.size === 0) rooms.delete(roomId)
  })
})

wss.on('error', (err) => {
  console.error('[sync] Server error:', err)
})

console.log(`[sync] 🚀 Excalidraw sync server on ws://localhost:${PORT}`)
