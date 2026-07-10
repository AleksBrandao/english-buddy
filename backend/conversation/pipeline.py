"""
Pipeline compartilhado: STT (Whisper) + LLM (Groq) + TTS (Piper).

Os modelos são carregados uma única vez quando este módulo é importado
(ou seja, uma vez quando o servidor Daphne sobe), não a cada mensagem.
"""

import os
import time
import subprocess

from dotenv import load_dotenv
from faster_whisper import WhisperModel
from groq import Groq

load_dotenv()  # carrega variáveis do arquivo .env, se existir

# ==== CONFIG ====
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY não encontrada. Crie um arquivo .env na pasta backend/ "
        "com a linha: GROQ_API_KEY=sua_key_aqui"
    )

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
PIPER_PATH = os.path.join(BASE_DIR, "piper", "piper.exe")
MODEL_PATH = os.path.join(BASE_DIR, "piper", "voices", "en_US-lessac-medium.onnx")

SYSTEM_PROMPT_TEMPLATE = """You are a friendly English conversation partner, talking as if on a walk with a friend.

The student's estimated level is: {nivel}.
{referencia_bloco}

STRICT RULES:
1. Match your vocabulary and grammar complexity to level {nivel}. Do not use idioms, phrasal verbs, or advanced expressions (e.g. "fingers crossed", "call it done") unless the student is at B2 or above.
2. Keep sentences short and use simple connectors (and, but, so, because). Avoid nested subordinate clauses.
3. If the student makes a grammar mistake, do NOT correct them directly. Instead, naturally repeat their idea back using the correct form (a "recast") as part of your response.
4. Ask only ONE question per response, and keep it simple.
5. Keep responses to 1-2 short sentences maximum.
6. Introduce at most one slightly new word or structure per response (slightly above their level, not two steps above).
7. Never lecture about grammar. Just model correct English naturally through conversation.

Respond only with what you would say out loud in the conversation — no meta-commentary."""


def montar_system_prompt(nivel: str = "A2/B1 (intermediate-beginner)", referencia: str = "") -> str:
    referencia_bloco = ""
    if referencia:
        referencia_bloco = (
            f"Concrete calibration anchor (important): the student has confirmed they "
            f"comfortably understand the following type of content: \"{referencia}\". "
            f"Use this as your real reference point for vocabulary and speed, not just the label above."
        )
    return SYSTEM_PROMPT_TEMPLATE.format(nivel=nivel, referencia_bloco=referencia_bloco)

# ==== CARREGADO UMA VEZ SÓ ====
print("[pipeline] Carregando modelo Whisper...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

groq_client = Groq(api_key=GROQ_API_KEY)
print("[pipeline] Pipeline pronto.")


def transcrever(caminho_audio: str):
    start = time.time()
    segments, info = whisper_model.transcribe(caminho_audio)  # detecta idioma automaticamente
    texto = " ".join([seg.text for seg in segments]).strip()
    latencia = time.time() - start
    return texto, latencia, info.language


def gerar_resposta(texto_usuario: str, historico=None, nivel: str = "A2/B1 (intermediate-beginner)", referencia: str = ""):
    start = time.time()

    messages = [{"role": "system", "content": montar_system_prompt(nivel, referencia)}]
    if historico:
        messages.extend(historico)
    messages.append({"role": "user", "content": texto_usuario})

    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=messages,
        max_tokens=500,
        reasoning_effort="low",
    )
    latencia = time.time() - start

    resposta = response.choices[0].message.content
    if not resposta or not resposta.strip():
        resposta = "Sorry, could you say that again?"

    return resposta, latencia


def falar(texto: str, caminho_saida: str, length_scale: float = 1.0):
    start = time.time()

    processo = subprocess.run(
        [
            PIPER_PATH,
            "--model", MODEL_PATH,
            "--output_file", caminho_saida,
            "--length_scale", str(length_scale),
        ],
        input=texto.encode("utf-8"),
        capture_output=True,
    )

    latencia = time.time() - start
    if processo.returncode != 0:
        erro = processo.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Piper falhou (returncode={processo.returncode}): {erro}")
    if not os.path.exists(caminho_saida):
        raise RuntimeError(
            f"Piper terminou sem erro mas não gerou o arquivo: {caminho_saida}"
        )
    return caminho_saida, latencia


# Frases que indicam pedido explícito de mudança de velocidade
PEDIDOS_MAIS_DEVAGAR = ("more slowly", "slower", "speak slow", "too fast")
PEDIDOS_NORMAL_VELOCIDADE = ("normal speed", "speak faster", "faster please")


def ajustar_velocidade(texto_usuario: str, velocidade_atual: float) -> float:
    """Detecta pedidos explícitos do usuário para ajustar a velocidade da fala.
    length_scale do Piper: 1.0 = normal, >1.0 = mais devagar, <1.0 = mais rápido."""
    texto_lower = texto_usuario.lower()

    if any(p in texto_lower for p in PEDIDOS_MAIS_DEVAGAR):
        return min(velocidade_atual + 0.25, 1.8)  # limite pra não ficar exagerado

    if any(p in texto_lower for p in PEDIDOS_NORMAL_VELOCIDADE):
        return max(velocidade_atual - 0.25, 0.9)

    return velocidade_atual


def velocidade_base_por_nivel(nivel: str) -> float:
    """Ajusta velocidade padrão conforme o nível estimado - iniciantes
    começam com fala um pouco mais devagar por padrão."""
    if nivel.startswith("A2"):
        return 1.15
    return 1.0


# ==== MODO DE PRÁTICA DE PRONÚNCIA ====
import difflib


def pedido_ajuda_em_portugues(texto: str, idioma_detectado: str) -> bool:
    """Detecta se o usuário está pedindo ajuda em português (ex: 'como eu falo...')."""
    if idioma_detectado != "pt":
        return False
    gatilhos = ("como eu falo", "como se fala", "como falar", "como pronunciar", "me ajuda a falar")
    texto_lower = texto.lower()
    return any(g in texto_lower for g in gatilhos)


def extrair_frase_alvo(pedido_portugues: str) -> str:
    """Usa o LLM para identificar a frase em inglês que o usuário quer aprender a falar."""
    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": (
                    "The user is a Brazilian Portuguese speaker asking, in Portuguese, "
                    "how to say something in English. Reply with ONLY the English phrase "
                    "they should practice saying, nothing else - no quotes, no explanation."
                ),
            },
            {"role": "user", "content": pedido_portugues},
        ],
        max_tokens=100,
        reasoning_effort="low",
    )
    return response.choices[0].message.content.strip().strip('"')


def avaliar_tentativa_pronuncia(tentativa: str, frase_alvo: str) -> tuple[bool, float]:
    """Compara a tentativa do usuário com a frase-alvo usando similaridade de texto.
    Retorna (acertou, similaridade de 0 a 1)."""
    a = tentativa.lower().strip().rstrip(".?!")
    b = frase_alvo.lower().strip().rstrip(".?!")
    similaridade = difflib.SequenceMatcher(None, a, b).ratio()
    acertou = similaridade >= 0.8
    return acertou, similaridade


# ==== ESTIMADOR SIMPLES DE NÍVEL ====
# Heurística leve (sem NLP pesado) baseada em: tamanho médio de frase,
# diversidade de vocabulário e uso de estruturas mais avançadas (subordinadas).
# Isso é um ponto de partida - pode evoluir para algo mais sofisticado depois.

CONECTORES_AVANCADOS = {
    "although", "however", "whereas", "despite", "nevertheless",
    "moreover", "furthermore", "provided that", "unless", "whereby",
}


def estimar_nivel(historico_falas: list[str], nivel_previo: str = None) -> str:
    """Recebe uma lista com as últimas falas transcritas do usuário e
    retorna uma estimativa simples de nível CEFR."""
    if not historico_falas:
        return nivel_previo or "A2/B1 (intermediate-beginner)"

    texto_completo = " ".join(historico_falas).lower()
    palavras = texto_completo.split()

    if len(palavras) < 5:
        return "A2/B1 (intermediate-beginner)"

    palavras_unicas = set(palavras)
    diversidade = len(palavras_unicas) / len(palavras)

    media_palavras_por_frase = len(palavras) / max(texto_completo.count("."), 1)

    usa_conectores_avancados = any(c in texto_completo for c in CONECTORES_AVANCADOS)

    pontos = 0
    if diversidade > 0.6:
        pontos += 1
    if media_palavras_por_frase > 12:
        pontos += 1
    if usa_conectores_avancados:
        pontos += 1

    if pontos >= 2:
        return "B2 (upper-intermediate)"
    elif pontos == 1:
        return "B1 (intermediate)"
    else:
        return "A2 (elementary-intermediate)"