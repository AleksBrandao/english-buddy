import { useState, useRef, useCallback, useEffect } from 'react'
import './App.css'

const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_URL = `${WS_PROTOCOL}//${window.location.host}/ws/talk/`

const PALAVRA_ATIVACAO = 'hi my friend'
const SILENCIO_LIMIAR = 0.025
const SILENCIO_DURACAO_MS = 1800
const EMA_ALPHA = 0.15
const TIMEOUT_VOLTAR_STANDBY_MS = 20000

const SCORE_LABELS = [
  ['task_completion', 'Conclusão'],
  ['clarity', 'Clareza'],
  ['fluency', 'Fluência'],
  ['organization', 'Organização'],
  ['interaction', 'Interação'],
]

function App() {
  const [status, setStatus] = useState('standby')
  const [mensagens, setMensagens] = useState([])
  const [conectado, setConectado] = useState(false)
  const [modo, setModo] = useState('free')
  const [lessonStage, setLessonStage] = useState(null)
  const [lessonInfo, setLessonInfo] = useState(null)
  const [targetPhrases, setTargetPhrases] = useState([])
  const [answerCount, setAnswerCount] = useState(0)
  const [canFinishAttempt, setCanFinishAttempt] = useState(false)
  const [lessonError, setLessonError] = useState('')
  const [feedback, setFeedback] = useState(null)
  const [feedbackReady, setFeedbackReady] = useState(false)

  const wsRef = useRef(null)
  const audioCtxRef = useRef(null)
  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const silenceTimerRef = useRef(null)
  const analiserRef = useRef(null)
  const rafRef = useRef(null)
  const wakeRecognitionRef = useRef(null)
  const standbyTimerRef = useRef(null)
  const emConversaRef = useRef(false)
  const modoRef = useRef('free')
  const autoListenAfterAudioRef = useRef(false)

  useEffect(() => {
    modoRef.current = modo
  }, [modo])

  const conectar = useCallback(() => {
    return new Promise((resolve, reject) => {
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
      ws.onerror = (error) => {
        console.error('Erro no WebSocket:', error)
        setConectado(false)
        reject(error)
      }

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          const blob = new Blob([event.data], { type: 'audio/wav' })
          const url = URL.createObjectURL(blob)
          const audio = new Audio(url)

          setStatus('falando')

          audio.onended = () => {
            URL.revokeObjectURL(url)
            if (emConversaRef.current && autoListenAfterAudioRef.current) {
              iniciarGravacao()
            }
          }

          audio.onerror = () => {
            URL.revokeObjectURL(url)
            setLessonError('Não foi possível reproduzir o áudio do Buddy.')
          }

          audio.play().catch((error) => {
            console.error('Erro ao reproduzir áudio:', error)
            URL.revokeObjectURL(url)
            setLessonError('O navegador bloqueou a reprodução do áudio.')
          })
          return
        }

        const dados = JSON.parse(event.data)

        if (dados.type === 'connection_ready') {
          setModo(dados.mode || 'free')
          return
        }

        if (dados.type === 'transcription') {
          setMensagens((current) => [
            ...current,
            { autor: 'voce', texto: dados.text },
          ])
          setStatus('processando')
          return
        }

        if (dados.type === 'response_text') {
          autoListenAfterAudioRef.current = dados.modo !== 'guided_feedback'
          setMensagens((current) => [
            ...current,
            { autor: 'ia', texto: dados.text },
          ])
          return
        }

        if (dados.type === 'lesson_started') {
          setModo('lesson')
          setLessonStage(dados.stage)
          setLessonInfo({
            title: dados.title,
            objective: dados.objective,
            estimatedDuration: dados.estimated_duration_minutes,
          })
          setLessonError('')
          setFeedback(null)
          setFeedbackReady(false)
          setAnswerCount(0)
          setCanFinishAttempt(false)

          const introMessages = (dados.messages || []).map((texto) => ({
            autor: 'ia',
            texto,
          }))
          setMensagens(introMessages)
          setStatus('aula iniciada')
          return
        }

        if (dados.type === 'target_phrases') {
          setLessonStage(dados.stage)
          setTargetPhrases(dados.phrases || [])
          setStatus('prepare as expressões')
          return
        }

        if (dados.type === 'feedback_generating') {
          emConversaRef.current = false
          autoListenAfterAudioRef.current = false
          setFeedbackReady(false)
          setStatus('avaliando primeira tentativa')
          return
        }

        if (dados.type === 'intermediate_feedback') {
          emConversaRef.current = false
          autoListenAfterAudioRef.current = false
          setFeedback(dados.feedback || null)
          setFeedbackReady(true)
          setStatus('feedback pronto')
          return
        }

        if (dados.type === 'lesson_stage_changed') {
          setLessonStage(dados.stage)

          if (dados.stage === 'first_attempt' || dados.stage === 'second_attempt') {
            setAnswerCount(0)
            setCanFinishAttempt(false)
            setStatus('aguardando pergunta')
          } else if (dados.stage === 'first_feedback') {
            emConversaRef.current = false
            autoListenAfterAudioRef.current = false
            if (dados.feedback_ready) {
              setFeedbackReady(true)
              setStatus('feedback pronto')
            } else {
              setStatus('primeira tentativa concluída')
            }
          } else if (dados.stage === 'final_result') {
            emConversaRef.current = false
            autoListenAfterAudioRef.current = false
            setStatus('segunda tentativa concluída')
          }
          return
        }

        if (dados.type === 'attempt_turn_recorded') {
          setAnswerCount(dados.answer_count || 0)
          setCanFinishAttempt(Boolean(dados.can_finish))

          if (dados.attempt_complete) {
            emConversaRef.current = false
            autoListenAfterAudioRef.current = false
          }
          return
        }

        if (dados.type === 'lesson_status') {
          setLessonStage(dados.stage)
          return
        }

        if (dados.type === 'lesson_completed') {
          emConversaRef.current = false
          autoListenAfterAudioRef.current = false
          setLessonStage('completed')
          setStatus('aula encerrada')
          return
        }

        if (dados.type === 'mode_changed') {
          setModo(dados.mode)
          setLessonStage(null)
          setLessonInfo(null)
          setTargetPhrases([])
          setAnswerCount(0)
          setCanFinishAttempt(false)
          setFeedback(null)
          setFeedbackReady(false)
          setMensagens([])
          setStatus('standby')
          setLessonError('')
          emConversaRef.current = false
          autoListenAfterAudioRef.current = false
          setTimeout(() => iniciarEscutaAtivacao(), 100)
          return
        }

        if (dados.type === 'lesson_error') {
          setLessonError(dados.message)
          if (dados.code === 'feedback_audio_error') {
            setStatus('feedback pronto')
          } else {
            setStatus('erro na aula')
          }
        }
      }

      wsRef.current = ws
    })
  }, [])

  const enviarComando = useCallback(async (payload) => {
    try {
      await conectar()
      wsRef.current.send(JSON.stringify(payload))
    } catch (error) {
      console.error('Erro ao enviar comando:', error)
      setLessonError('Não foi possível conectar ao servidor.')
    }
  }, [conectar])

  const liberarMicrofone = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }

    if (audioCtxRef.current) {
      audioCtxRef.current.close()
      audioCtxRef.current = null
    }
  }, [])

  const resetarTimeoutStandby = useCallback(() => {
    if (modoRef.current !== 'free') return
    if (standbyTimerRef.current) clearTimeout(standbyTimerRef.current)

    standbyTimerRef.current = setTimeout(() => {
      emConversaRef.current = false
      liberarMicrofone()
      setStatus('standby')
      iniciarEscutaAtivacao()
    }, TIMEOUT_VOLTAR_STANDBY_MS)
  }, [liberarMicrofone])

  const pararGravacao = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
    silenceTimerRef.current = null
  }, [])

  const monitorarSilencio = useCallback(() => {
    const analiser = analiserRef.current
    if (!analiser) return

    const buffer = new Float32Array(analiser.fftSize)
    let volumeSuavizado = 0

    const checar = () => {
      analiser.getFloatTimeDomainData(buffer)

      let soma = 0
      for (let index = 0; index < buffer.length; index += 1) {
        soma += buffer[index] * buffer[index]
      }

      const volumeInstantaneo = Math.sqrt(soma / buffer.length)
      volumeSuavizado =
        EMA_ALPHA * volumeInstantaneo +
        (1 - EMA_ALPHA) * volumeSuavizado

      if (volumeSuavizado > SILENCIO_LIMIAR) {
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current)
          silenceTimerRef.current = null
        }
      } else if (!silenceTimerRef.current) {
        silenceTimerRef.current = setTimeout(
          () => pararGravacao(),
          SILENCIO_DURACAO_MS,
        )
      }

      rafRef.current = requestAnimationFrame(checar)
    }

    checar()
  }, [pararGravacao])

  const iniciarGravacao = useCallback(async () => {
    if (
      recorderRef.current &&
      recorderRef.current.state === 'recording'
    ) {
      return
    }

    try {
      resetarTimeoutStandby()
      await conectar()

      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setStatus('erro: não foi possível conectar ao servidor')
        return
      }

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

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }

      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const arrayBuffer = await blob.arrayBuffer()

        stream.getTracks().forEach((track) => track.stop())
        streamRef.current = null

        if (audioCtx.state !== 'closed') await audioCtx.close()
        audioCtxRef.current = null
        analiserRef.current = null

        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(arrayBuffer)
          setStatus('processando')
        } else {
          setStatus('erro: sem conexão com o servidor')
          emConversaRef.current = false
        }
      }

      recorder.start()
      setStatus('ouvindo')
      monitorarSilencio()
    } catch (error) {
      console.error('Erro ao iniciar gravação:', error)
      setStatus('erro ao acessar o microfone')
      liberarMicrofone()
    }
  }, [conectar, liberarMicrofone, monitorarSilencio, resetarTimeoutStandby])

  const iniciarEscutaAtivacao = useCallback(() => {
    if (modoRef.current !== 'free') return

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      setStatus('reconhecimento por palavra de ativação indisponível')
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
      const ultimaFala =
        event.results[event.results.length - 1][0].transcript.toLowerCase()

      if (ultimaFala.includes(PALAVRA_ATIVACAO)) {
        recognition.stop()
        emConversaRef.current = true
        autoListenAfterAudioRef.current = true
        iniciarGravacao()
      }
    }

    recognition.onend = () => {
      if (!emConversaRef.current && modoRef.current === 'free') {
        recognition.start()
      }
    }

    recognition.start()
    wakeRecognitionRef.current = recognition
  }, [iniciarGravacao])

  const iniciarAula = useCallback(async () => {
    setLessonError('')
    if (wakeRecognitionRef.current) wakeRecognitionRef.current.stop()
    emConversaRef.current = true
    autoListenAfterAudioRef.current = false
    await enviarComando({
      type: 'start_lesson',
      scenario_id: 'daily-routine-01',
    })
  }, [enviarComando])

  const continuarAula = useCallback(async () => {
    emConversaRef.current = true
    autoListenAfterAudioRef.current = false
    await enviarComando({ type: 'continue_lesson' })
  }, [enviarComando])

  const iniciarSegundaTentativa = useCallback(async () => {
    setLessonError('')
    emConversaRef.current = true
    autoListenAfterAudioRef.current = false
    setFeedbackReady(false)
    await enviarComando({ type: 'start_second_attempt' })
  }, [enviarComando])

  const encerrarTentativa = useCallback(async () => {
    emConversaRef.current = false
    autoListenAfterAudioRef.current = false
    await enviarComando({ type: 'finish_attempt' })
  }, [enviarComando])

  const encerrarAula = useCallback(async () => {
    emConversaRef.current = false
    autoListenAfterAudioRef.current = false
    liberarMicrofone()
    await enviarComando({ type: 'finish_lesson' })
  }, [enviarComando, liberarMicrofone])

  const voltarConversaLivre = useCallback(async () => {
    liberarMicrofone()
    await enviarComando({
      type: 'start_free_conversation',
      finish_active_lesson: true,
    })
  }, [enviarComando, liberarMicrofone])

  useEffect(() => {
    conectar()
    iniciarEscutaAtivacao()

    return () => {
      if (wakeRecognitionRef.current) wakeRecognitionRef.current.stop()
      if (standbyTimerRef.current) clearTimeout(standbyTimerRef.current)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (wsRef.current) wsRef.current.close()
      liberarMicrofone()
    }
  }, [])

  const showContinue =
    lessonStage === 'introduction' || lessonStage === 'phrase_preparation'
  const attemptActive =
    lessonStage === 'first_attempt' || lessonStage === 'second_attempt'

  return (
    <div className="app">
      <h1>English Buddy</h1>
      <p className="status">
        Status: {status} {conectado ? '🟢' : '🔴'}
      </p>

      {modo === 'free' ? (
        <section className="mode-card">
          <h2>Conversa livre</h2>
          <p>
            Diga “{PALAVRA_ATIVACAO}” para começar ou pratique uma aula guiada.
          </p>
          <button onClick={iniciarAula} disabled={!conectado}>
            Iniciar Daily Routine
          </button>
        </section>
      ) : (
        <section className="mode-card lesson-card">
          <span className="lesson-label">Prática guiada</span>
          <h2>{lessonInfo?.title || 'Daily Routine'}</h2>
          {lessonInfo?.objective && <p>{lessonInfo.objective}</p>}
          <p className="lesson-stage">Etapa: {lessonStage}</p>

          {targetPhrases.length > 0 && lessonStage === 'phrase_preparation' && (
            <div className="phrases">
              <strong>Expressões úteis</strong>
              {targetPhrases.map((phrase) => (
                <span key={phrase}>{phrase}</span>
              ))}
            </div>
          )}

          {attemptActive && (
            <p className="attempt-progress">
              Respostas nesta tentativa: {answerCount}
              {canFinishAttempt ? ' — mínimo atingido' : ''}
            </p>
          )}

          {lessonStage === 'first_feedback' && feedback && (
            <div className="feedback-panel">
              <div className="feedback-heading">
                <div>
                  <span className="feedback-kicker">Seu feedback</span>
                  <h3>Primeira tentativa</h3>
                </div>
                <span className="feedback-source">
                  {feedback.source === 'fallback' ? 'avaliação local' : 'avaliação IA'}
                </span>
              </div>

              <div className="score-grid">
                {SCORE_LABELS.map(([field, label]) => (
                  <div className="score-item" key={field}>
                    <span>{label}</span>
                    <strong>{feedback[field] ?? '-'} / 5</strong>
                  </div>
                ))}
              </div>

              <div className="feedback-section">
                <strong>Ponto positivo</strong>
                <p>{feedback.strengths?.[0]}</p>
              </div>

              <div className="feedback-section">
                <strong>Prioridade para repetir melhor</strong>
                <p>{feedback.priority_improvements?.[0]?.suggestion}</p>
              </div>

              <div className="feedback-example">
                <strong>Exemplo aprimorado</strong>
                <p>{feedback.improved_example}</p>
              </div>

              {feedback.target_phrases_used?.length > 0 && (
                <div className="feedback-section">
                  <strong>Expressões utilizadas</strong>
                  <div className="used-phrases">
                    {feedback.target_phrases_used.map((phrase) => (
                      <span key={phrase}>{phrase}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="lesson-actions">
            {showContinue && (
              <button onClick={continuarAula}>Continuar</button>
            )}

            {lessonStage === 'first_feedback' && !feedbackReady && (
              <p className="notice">Preparando seu feedback...</p>
            )}

            {lessonStage === 'first_feedback' && feedbackReady && (
              <button onClick={iniciarSegundaTentativa}>
                Iniciar segunda tentativa
              </button>
            )}

            {attemptActive && canFinishAttempt && (
              <button className="secondary" onClick={encerrarTentativa}>
                Encerrar esta tentativa
              </button>
            )}

            {lessonStage === 'final_result' && (
              <p className="notice">
                Segunda tentativa registrada. A comparação final será o próximo incremento.
              </p>
            )}

            {lessonStage !== 'completed' && (
              <button className="danger" onClick={encerrarAula}>
                Encerrar aula
              </button>
            )}

            <button className="secondary" onClick={voltarConversaLivre}>
              Voltar à conversa livre
            </button>
          </div>
        </section>
      )}

      {lessonError && <p className="error-message">{lessonError}</p>}

      <div className="conversa">
        {mensagens.map((mensagem, index) => (
          <div key={index} className={`mensagem ${mensagem.autor}`}>
            <strong>{mensagem.autor === 'voce' ? 'Você' : 'Buddy'}:</strong>{' '}
            {mensagem.texto}
          </div>
        ))}
      </div>
    </div>
  )
}

export default App
