import hmac
import json
import os

from dotenv import load_dotenv
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .pipeline import gerar_resposta


load_dotenv()

ALEXA_BACKEND_TOKEN = os.getenv("ALEXA_BACKEND_TOKEN", "")
MAX_TEXT_LENGTH = 1500
MAX_HISTORY_MESSAGES = 8


def _limpar_historico(history):
    if not isinstance(history, list):
        return []

    clean_history = []

    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()

        if not content:
            continue

        clean_history.append(
            {
                "role": role,
                "content": content[:MAX_TEXT_LENGTH],
            }
        )

    return clean_history


@csrf_exempt
@require_POST
def alexa_respond(request):
    received_token = request.headers.get("X-Alexa-Token", "")

    if not ALEXA_BACKEND_TOKEN:
        return JsonResponse(
            {"error": "ALEXA_BACKEND_TOKEN não configurado"},
            status=503,
        )

    if not hmac.compare_digest(received_token, ALEXA_BACKEND_TOKEN):
        return JsonResponse({"error": "Não autorizado"}, status=401)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    text = body.get("text", "")

    if not isinstance(text, str) or not text.strip():
        return JsonResponse(
            {"error": "O campo text é obrigatório"},
            status=400,
        )

    text = text.strip()[:MAX_TEXT_LENGTH]
    history = _limpar_historico(body.get("history", []))

    try:
        reply, latency = gerar_resposta(
            texto_usuario=text,
            historico=history,
        )
    except Exception as exc:
        print(f"[alexa] Erro ao gerar resposta: {exc}")
        return JsonResponse(
            {"error": "Falha ao gerar resposta"},
            status=500,
        )

    new_history = (
        history
        + [{"role": "user", "content": text}]
        + [{"role": "assistant", "content": reply}]
    )[-MAX_HISTORY_MESSAGES:]

    return JsonResponse(
        {
            "reply": reply.strip(),
            "history": new_history,
            "latency_seconds": round(latency, 3),
        }
    )