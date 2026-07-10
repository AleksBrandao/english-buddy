import { useState, useRef, useCallback, useEffect } from 'react'
import './App.css'

const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_URL = `${WS_PROTOCOL}//${window.location.host}/ws/talk/`

const PALAVRA_ATIVACAO = 'hi my friend'
const SILENCIO_LIMIAR = 0.015
const SILENCIO_DURACAO_MS = 1200
const TIMEOUT_VOLTAR_STANDBY_MS = 20000 // volta a esperar a palavra de ativação após tanto tempo sem fala

function App() {
  const [status, setStatus] = useState('standby') // standby | ouvindo | processando | falando
  const [mensagens, setMensagens] = useState([])
  const [conectado, setConectado] = useState(false)

  const wsRef = useRef(null)
  const audioCtxRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const silenceTimerRef = useRef(null)
  const analiserRef = useRef(null)
  const rafRef = useRef(null)
  const wakeRecognitionRef = useRef(null)
  const standbyTimerRef = useRef(null)
  const emConversaRef = useRef(false)

  const conectar = useCallback(() => {
    return new Promise((resolve) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        resolve()
        return
      }

      const ws = new WebSocket(WS_URL)
      ws.binaryType = 'arraybuffer'

      ws.onopen = () => {
        setConectado(true)
        resolve()
      }
      ws.onclose = () => setConectado(false)
      ws.onerror = (err) => {
        console.error('Erro no WebSocket:', err)
        setConectado(false)
      }

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: 'audio/wav' })
        const url = URL.createObjectURL(blob)
        setStatus('falando')
        const audio = new Audio(url)
        audio.play()
        audio.onended = () => {
          // Depois de falar, volta a ouvir automaticamente (conversa fluida, sem botão)
          if (emConversaRef.current) {
            iniciarGravacao()
          }
        }
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
    })
  }, [])

  const resetarTimeoutStandby = useCallback(() => {
    if (standbyTimerRef.current) clearTimeout(standbyTimerRef.current)
    standbyTimerRef.current = setTimeout(() => {
      emConversaRef.current = false
      setStatus('standby')
      iniciarEscutaAtivacao()
    }, TIMEOUT_VOLTAR_STANDBY_MS)
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
        silenceTimerRef.current = setTimeout(() => pararGravacao(), SILENCIO_DURACAO_MS)
      }

      rafRef.current = requestAnimationFrame(checar)
    }

    checar()
  }, [pararGravacao])

  const iniciarGravacao = useCallback(async () => {
    resetarTimeoutStandby()
    await conectar()

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setStatus('erro: não foi possível conectar ao servidor')
      return
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
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

      stream.getTracks().forEach((t) => t.stop())
      audioCtx.close()

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(arrayBuffer)
        setStatus('processando')
      } else {
        console.error('WebSocket não está conectado. Estado:', wsRef.current?.readyState)
        setStatus('erro: sem conexão com o servidor')
        emConversaRef.current = false
      }
    }

    recorder.start()
    setStatus('ouvindo')
    monitorarSilencio()
  }, [conectar, monitorarSilencio, resetarTimeoutStandby])

  // ==== DETECÇÃO DA PALAVRA DE ATIVAÇÃO (sempre ouvindo, leve) ====
  const iniciarEscutaAtivacao = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Reconhecimento de voz não suportado neste navegador. Use Chrome no Android.')
      return
    }

    if (wakeRecognitionRef.current) {
      wakeRecognitionRef.current.stop()
    }

    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event) => {
      const ultimaFala = event.results[event.results.length - 1][0].transcript.toLowerCase()

      if (ultimaFala.includes(PALAVRA_ATIVACAO)) {
        recognition.stop()
        emConversaRef.current = true
        iniciarGravacao()
      }
    }

    recognition.onend = () => {
      // Reinicia sozinho enquanto estiver em modo standby (a API para sozinha às vezes)
      if (!emConversaRef.current) {
        recognition.start()
      }
    }

    recognition.start()
    wakeRecognitionRef.current = recognition
  }, [iniciarGravacao])

  useEffect(() => {
    conectar()
    iniciarEscutaAtivacao()
    return () => {
      if (wakeRecognitionRef.current) wakeRecognitionRef.current.stop()
      if (standbyTimerRef.current) clearTimeout(standbyTimerRef.current)
    }
  }, [])

  return (
    <div className="app">
      <h1>English Buddy</h1>
      <p className="status">
        Status: {status} {conectado ? '🟢' : '🔴'}
      </p>
      <p className="dica">
        {status === 'standby'
          ? `Diga "${PALAVRA_ATIVACAO}" para começar`
          : 'Conversa em andamento...'}
      </p>

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
