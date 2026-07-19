import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

const params = new URLSearchParams(window.location.search)
const room = params.get('room') || 'default-room'
const sessionId = params.get('sessionId') || 'unknown'

function handleClose() {
  window.parent.postMessage({ type: 'close-whiteboard' }, '*')
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <App room={room} sessionId={sessionId} onClose={handleClose} />
)
