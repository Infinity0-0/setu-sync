import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Excalidraw } from '@excalidraw/excalidraw'
import './mobile-fixes.css'
import '@excalidraw/excalidraw/index.css'
import './index.css'

// ── Stable colour palette for collaborators ──────────────────────────────────
const COLLAB_COLORS = [
  '#f87171', '#fb923c', '#fbbf24', '#34d399',
  '#38bdf8', '#818cf8', '#e879f9', '#f472b6',
]
function colorForId(id) {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return COLLAB_COLORS[h % COLLAB_COLORS.length]
}

// ── Throttle helper ────────────────────────────────────────────────────
function throttle(fn, ms) {
  let last = 0, rafId = null
  return (...args) => {
    const now = Date.now()
    if (now - last >= ms) {
      last = now
      // Use RAF so we never paint mid-frame
      if (rafId) cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => { rafId = null; fn(...args) })
    }
  }
}

// ── Max message size guard ─────────────────────────────────────────────────
const MAX_MSG_BYTES = 512 * 1024 // 512 KB — refuse to send anything larger

export default function App({ room, sessionId, onClose }) {
  // ── Stable IDs ─────────────────────────────────────────────────────────────
  const userIdRef = useRef(
    sessionId && sessionId !== 'unknown'
      ? sessionId
      : `user-${Math.random().toString(36).slice(2, 10)}`
  )
  const userNameRef = useRef(
    sessionId && sessionId !== 'unknown' ? sessionId : 'Mobile User'
  )
  const userId   = userIdRef.current
  const userName = userNameRef.current

  // ── Refs shared across callbacks ───────────────────────────────────────────
  const excalidrawAPIRef    = useRef(null)
  const wsRef               = useRef(null)
  const reconnectDelayRef   = useRef(2000)
  const reconnectTimerRef   = useRef(null)
  const isConnectedRef      = useRef(false)
  const collaboratorsRef    = useRef(new Map())
  const lastBroadcastedVersions = useRef(new Map())
  const isMountedRef        = useRef(true)

  // ── UI state ───────────────────────────────────────────────────────────────
  const [connStatus, setConnStatus] = useState('connecting') // 'connecting'|'live'|'error'|'expired'

  // ── WebSocket URL ──────────────────────────────────────────────────────────
  const API_HOST =
      window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
          ? "localhost:8000"
          : "setu-backend-txdk.onrender.com";

  const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const syncUri = `${wsProto}://${API_HOST}/api/excalidraw/sync/${encodeURIComponent(room)}?sessionId=${encodeURIComponent(userId)}&name=${encodeURIComponent(userName)}`

  // ── Apply remote drawing update (RAF-batched for smoothness) ─────────────────────
  const pendingElementsRef = useRef(null) // batch remote element updates
  const rafPendingRef      = useRef(null)

  const applyRemoteUpdate = useCallback((payload, senderId) => {
    if (!payload || !isMountedRef.current) return
    const api = excalidrawAPIRef.current
    if (!api) return

    if (payload.action === 'elements' && Array.isArray(payload.elements)) {
      // Accumulate changes then flush on next animation frame
      if (!pendingElementsRef.current) pendingElementsRef.current = new Map()
      payload.elements.forEach(el => pendingElementsRef.current.set(el.id, el))

      if (!rafPendingRef.current) {
        rafPendingRef.current = requestAnimationFrame(() => {
          rafPendingRef.current = null
          if (!isMountedRef.current || !pendingElementsRef.current) return
          const pending = pendingElementsRef.current
          pendingElementsRef.current = null
          const current  = api.getSceneElements()
          const merged = current
            .map(el => pending.has(el.id) ? { ...el, ...pending.get(el.id) } : el)
            .concat(
              [...pending.values()].filter(el => !current.find(c => c.id === el.id))
            )
          api.updateScene({ elements: merged, commitToHistory: false })
        })
      }
    } else if (payload.action === 'pointer' && payload.pointer) {
      // Pointer updates: batch via RAF so cursor is always smooth
      const userColor = colorForId(senderId)
      requestAnimationFrame(() => {
        if (!isMountedRef.current) return
        const updated = new Map(collaboratorsRef.current)
        updated.set(senderId, {
          pointer:  { x: payload.pointer.x, y: payload.pointer.y },
          username: payload.name || senderId.slice(0, 8),
          color:    { background: userColor, stroke: '#fff' },
          id:       senderId,
        })
        collaboratorsRef.current = updated
        api.updateScene({ collaborators: updated })
      })
    } else if (payload.action === 'clear') {
      api.resetScene()
    }
  }, [])

  // ── Send helper (with size guard) ──────────────────────────────────────────
  const safeSend = useCallback((obj) => {
    const ws = wsRef.current
    if (!ws || !isConnectedRef.current || ws.readyState !== WebSocket.OPEN) return
    try {
      const str = JSON.stringify(obj)
      if (str.length > MAX_MSG_BYTES) return // silently drop oversized payloads
      ws.send(str)
    } catch { /* ignore */ }
  }, [])

  // ── Connect / Reconnect ───────────────────────────────────────────────────
  const connectWs = useCallback(() => {
    if (!room || !isMountedRef.current) return
    setConnStatus('connecting')

    const ws = new WebSocket(syncUri)
    wsRef.current = ws

    ws.onopen = () => {
      if (!isMountedRef.current) { ws.close(); return }
      isConnectedRef.current = true
      reconnectDelayRef.current = 2000
      setConnStatus('live')
    }

    ws.onmessage = async (event) => {
      if (!isMountedRef.current) return
      try {
        const raw = event.data instanceof Blob ? await event.data.text() : event.data
        if (raw.length > MAX_MSG_BYTES * 4) return // guard oversized incoming
        const msg = JSON.parse(raw)
        if (msg.type === 'whiteboard_draw') {
          applyRemoteUpdate(msg.payload, msg.sender)
        } else if (msg.type === 'scene_request' && excalidrawAPIRef.current) {
          // A new user joined — send them the current scene
          const elements = excalidrawAPIRef.current.getSceneElements()
          safeSend({
            type: 'scene_snapshot',
            sender: userId,
            target: msg.sender,
            payload: { action: 'elements', elements },
          })
        } else if (msg.type === 'scene_snapshot') {
          // Receiving initial scene state from an existing client
          applyRemoteUpdate(msg.payload, msg.sender)
        }
      } catch { /* ignore bad JSON */ }
    }

    ws.onclose = (ev) => {
      isConnectedRef.current = false
      if (!isMountedRef.current) return
      if (ev.code === 4004) { setConnStatus('expired'); return } // room closed
      setConnStatus('error')
      const delay = reconnectDelayRef.current
      reconnectDelayRef.current = Math.min(delay * 1.5, 10000)
      reconnectTimerRef.current = setTimeout(connectWs, delay)
    }

    ws.onerror = () => { /* onclose fires immediately after */ }
  }, [room, syncUri, applyRemoteUpdate])

  useEffect(() => {
    isMountedRef.current = true
    connectWs()
    return () => {
      isMountedRef.current = false
      clearTimeout(reconnectTimerRef.current)
      const ws = wsRef.current
      if (ws) { ws.onclose = null; ws.close() }
    }
  }, [connectWs])

  // ── onChange: ~30 fps element broadcast ─────────────────────────────────────
  const broadcastElements = useCallback(
    throttle((elements) => {
      const versions = lastBroadcastedVersions.current
      const changed = elements.filter(el => {
        if (versions.get(el.id) === el.version) return false
        versions.set(el.id, el.version)
        return true
      })
      if (changed.length === 0) return
      
      safeSend({
        type:   'whiteboard_draw',
        sender: userId,
        payload: { action: 'elements', elements: changed },
      })
    }, 33), // ~30 fps for smooth real-time drawing
    [safeSend, userId]
  )

  const onChange = useCallback((elements) => {
    broadcastElements(elements)
  }, [broadcastElements])

  // ── onPointerUpdate: ~60 fps cursor broadcast ────────────────────────────────
  const broadcastPointer = useCallback(
    throttle((pointer) => {
      safeSend({
        type:   'whiteboard_draw',
        sender: userId,
        payload: { action: 'pointer', pointer, name: userName },
      })
    }, 16), // ~60 fps — silky smooth cursor for collaborators
    [safeSend, userId, userName]
  )

  // ── onPointerUpdate: throttled cursor broadcast ───────────────────────────
  const onPointerUpdate = useCallback((payload) => {
    if (payload?.pointer) broadcastPointer(payload.pointer)
  }, [broadcastPointer])

  // ── excalidrawAPI callback ─────────────────────────────────────────────────
  const excalidrawAPICallback = useCallback((api) => {
    excalidrawAPIRef.current = api
  }, [])

  // ── Status badge colours ───────────────────────────────────────────────────
  const statusConfig = {
    connecting: { bg: '#6366f1', icon: '⟳', text: 'Connecting…' },
    live:       { bg: '#10b981', icon: '●', text: 'Live Sync'   },
    error:      { bg: '#f59e0b', icon: '⚠', text: 'Reconnecting…' },
    expired:    { bg: '#ef4444', icon: '✕', text: 'Room Expired'  },
  }
  const sc = statusConfig[connStatus] || statusConfig.connecting

  return (
    <div style={{
      position:  'fixed',
      inset:     0,
      background: '#fff',
      zIndex:    1000,
      touchAction: 'none',
      WebkitUserSelect:         'none',
      WebkitTapHighlightColor:  'transparent',
    }}>
      {/* ── Top-right HUD ──────────────────────────────────────────────────── */}
      <div style={{
        position: 'absolute',
        top:   'max(6px, env(safe-area-inset-top))',
        right: 'max(12px, env(safe-area-inset-right))',
        zIndex: 2000,
        display: 'flex',
        gap: 8,
        alignItems: 'center',
        pointerEvents: 'none',
      }}>
        <span className="setu-live-badge" style={{
          background:   sc.bg,
          color:        '#fff',
          padding:      '5px 11px',
          borderRadius: 999,
          fontSize:     12,
          fontWeight:   600,
          letterSpacing: '.3px',
          userSelect:   'none',
        }}>
          {sc.icon} {sc.text}
        </span>
{/* Close button removed — parent handles it */}
      </div>

      {/* ── Excalidraw canvas ─────────────────────────────────────────────── */}
      <div className="excalidraw-wrapper" style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}>
        <Excalidraw
          excalidrawAPI={excalidrawAPICallback}
          onChange={onChange}
          onPointerUpdate={onPointerUpdate}
          isCollaborating={connStatus === 'live'}
          initialData={{ appState: { viewBackgroundColor: '#ffffff' } }}
        />
      </div>
    </div>
  )
}