# English Buddy 🎙️

Um amigo virtual para praticar conversação em inglês por voz — pensado para uso
enquanto caminha, com fone de ouvido, sem precisar tocar na tela.

Funciona 100% com processamento local (STT e TTS rodam no seu PC), usando a
Groq apenas para a geração de respostas (LLM).

## Como funciona

```
Voz (mic) → Whisper (STT) → Groq (LLM) → Piper (TTS) → Voz (alto-falante/fone)
```

- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modelo `base`, roda local em CPU)
- **LLM**: [Groq](https://groq.com) (`openai/gpt-oss-20b`) — gera as respostas da conversa
- **TTS**: [Piper](https://github.com/rhasspy/piper) (voz `en_US-lessac-medium`, roda local)
- **VAD**: `webrtcvad` — detecta quando você parou de falar, sem precisar de botão
- **Backend**: Django + Channels (WebSocket) orquestrando o pipeline
- **Frontend**: React + Vite

### Recursos pedagógicos

- Calibração automática de nível (CEFR estimado a partir da sua fala)
- Recasts em vez de correção direta (a IA repete sua frase corrigida naturalmente)
- Controle de velocidade da fala (ajustável durante a conversa, ex: *"speak more slowly"*)
- Modo de prática de pronúncia (peça ajuda em português, ex: *"como eu falo..."*)
- Persistência de conversas e nível entre sessões (banco de dados)
- Ativação por palavra-chave ("Hi my friend") + conversa contínua sem botão (mobile)
- Prática guiada inicial: **Talking about your daily routine**

## Pré-requisitos

- Python 3.11+
- Node.js 18+
- Uma [conta grátis na Groq](https://console.groq.com) (para a API key)
- [Piper](https://github.com/rhasspy/piper/releases) (executável + voz `en_US-lessac-medium`)

## Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/Scripts/activate  # Windows (Git Bash) — ajuste para seu shell
pip install -r requirements.txt
```

Cria um arquivo `.env` dentro de `backend/`:
```
GROQ_API_KEY=sua_key_aqui
```

Baixa o [Piper](https://github.com/rhasspy/piper/releases) e a voz
[`en_US-lessac-medium`](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium),
colocando em:
```
backend/piper/piper.exe
backend/piper/voices/en_US-lessac-medium.onnx
backend/piper/voices/en_US-lessac-medium.onnx.json
```

Aplica as migrations e sobe o servidor:
```bash
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Acessa `http://localhost:5173`.

## Prática guiada: Daily Routine

Na tela inicial, selecione **Iniciar Daily Routine**.

O fluxo disponível neste incremento é:

```text
Introdução
→ apresentação das expressões úteis
→ primeira tentativa por voz
→ registro automático de até seis respostas
→ encerramento da primeira tentativa
```

As respostas são persistidas em `SessaoTreino`, separadas do histórico da
conversa livre. O feedback automático e a segunda tentativa serão conectados no
incremento seguinte.

### Comandos WebSocket

O mesmo fluxo pode ser controlado enviando JSON para `/ws/talk/`:

```json
{"type": "start_lesson", "scenario_id": "daily-routine-01"}
```

```json
{"type": "continue_lesson"}
```

O primeiro `continue_lesson` apresenta as expressões. O segundo inicia a
primeira pergunta falada.

Outros comandos disponíveis:

```json
{"type": "lesson_status"}
{"type": "finish_attempt"}
{"type": "finish_lesson"}
{"type": "start_free_conversation", "finish_active_lesson": true}
```

## Uso pelo celular (fora de casa)

Para acessar de fora da rede local, usamos um túnel [ngrok](https://ngrok.com):

```bash
ngrok http 8000
```

Acesse a URL gerada pelo navegador do celular (Chrome/Android recomendado, para
suporte à detecção de palavra de ativação via Web Speech API).

> Para uso contínuo sem depender do PC ligado, uma evolução futura é hospedar
> o backend em um serviço como Render/Railway e o frontend na Vercel.

## Painel administrativo

Para inspecionar conversas, sessões guiadas, avaliações e ajustar o perfil de
nível salvo:

```bash
python manage.py createsuperuser
```

Depois acesse `http://localhost:8000/admin/`.

## Estrutura do projeto

```
english-buddy/
├── backend/
│   ├── config/                    # settings do Django
│   ├── conversation/              # app principal
│   │   ├── pipeline.py            # lógica de STT + LLM + TTS
│   │   ├── consumers.py           # WebSocket e modos livre/guiado
│   │   ├── lesson_orchestrator.py # estados da prática guiada
│   │   ├── scenarios/             # conteúdo dos cenários
│   │   └── models.py              # perfil, conversas e sessões
│   └── piper/                      # binário e vozes do Piper (não versionado)
└── frontend/
    └── src/
        └── App.jsx                 # conversa por voz e prática guiada
```

## Roadmap / ideias futuras

- [ ] Feedback automático da primeira tentativa
- [ ] Segunda tentativa e comparação de evolução
- [ ] Verificação de pronúncia baseada em áudio (não só texto transcrito)
- [ ] Deploy em produção (Vercel + Render/Railway), sem depender do PC ligado
- [ ] Multiusuário com autenticação
- [ ] Estimador de nível mais robusto (NLP em vez de heurística simples)
