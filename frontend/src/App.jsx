import { useState, useRef, useCallback } from 'react'
import './App.css'

const WS_URL = 'ws://localhost:8000/ws/talk/'
const SILENCIO_LIMIAR = 0.015        // ajuste conforme sensibilidade do seu mic
const SILENCIO_DURACAO_MS = 1200     // tempo de silêncio pra considerar que parou de falar

function App() {
  const [status, setStatus] = useState('parado') // parado | ouvindo | processando | falando
  const [mensagens, setMensagens] = useState([])
  const [conectado, setConectado] = useState(false)

  const wsRef = useRef(null)
  const audioCtxRef = useRef(null)
  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const silenceTimerRef = useRef(null)
  const analiserRef = useRef(null)
  const rafRef = useRef(null)

  const conectar = useCallback(() => {
    const ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => setConectado(true)
    ws.onclose = () => setConectado(false)

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // áudio de resposta
        const blob = new Blob([event.data], { type: 'audio/wav' })
        const url = URL.createObjectURL(blob)
        setStatus('falando')
        const audio = new Audio(url)
        audio.play()
        audio.onended = () => setStatus('parado')
        return
      }

      const dados = JSON.parse(event.data)
      if (dados.type === 'transcription') {
        setMensagens((m) => [...m, { autor: 'voce', texto: dados.text }])
        setStatus('processando')
      } else if (dados.type === 'response_text') {
        setMensagens((m) => [...m, { autor: 'ia', texto: dados.text }])
      }
    }

    wsRef.current = ws
  }, [])

  const pararGravacao = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
  }, [])

  const monitorarSilencio = useCallback(() => {
    const analiser = analiserRef.current
    const buffer = new Float32Array(analiser.fftSize)

    const checar = () => {
      analiser.getFloatTimeDomainData(buffer)
      let soma = 0
      for (let i = 0; i < buffer.length; i++) soma += buffer[i] * buffer[i]
      const volume = Math.sqrt(soma / buffer.length)

      if (volume > SILENCIO_LIMIAR) {
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current)
          silenceTimerRef.current = null
        }
      } else if (!silenceTimerRef.current) {
        silenceTimerRef.current = setTimeout(() => {
          pararGravacao()
        }, SILENCIO_DURACAO_MS)
      }

      rafRef.current = requestAnimationFrame(checar)
    }

    checar()
  }, [pararGravacao])

  const iniciarGravacao = useCallback(async () => {
    if (!conectado) conectar()

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream

    const audioCtx = new AudioContext()
    audioCtxRef.current = audioCtx
    const source = audioCtx.createMediaStreamSource(stream)
    const analiser = audioCtx.createAnalyser()
    analiser.fftSize = 2048
    source.connect(analiser)
    analiserRef.current = analiser

    const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    recorderRef.current = recorder
    chunksRef.current = []

    recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
      const arrayBuffer = await blob.arrayBuffer()

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(arrayBuffer)
      }

      stream.getTracks().forEach((t) => t.stop())
      audioCtx.close()
      setStatus('processando')
    }

    recorder.start()
    setStatus('ouvindo')
    monitorarSilencio()
  }, [conectado, conectar, monitorarSilencio])

  return (
    <div className="app">
      <h1>English Buddy</h1>
      <p className="status">Status: {status} {conectado ? '🟢' : '🔴'}</p>

      <button
        onClick={iniciarGravacao}
        disabled={status === 'ouvindo' || status === 'processando'}
      >
        {status === 'ouvindo' ? 'Ouvindo...' : 'Falar'}
      </button>

      <div className="conversa">
        {mensagens.map((m, i) => (
          <div key={i} className={`mensagem ${m.autor}`}>
            <strong>{m.autor === 'voce' ? 'Você' : 'Buddy'}:</strong> {m.texto}
          </div>
        ))}
      </div>
    </div>
  )
}

export default App
