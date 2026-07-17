import hashlib
import hmac
import json
import os
import re

from dotenv import load_dotenv
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Conversa, InteracaoAlexa, Mensagem, Perfil


load_dotenv()

ALEXA_BACKEND_TOKEN = os.getenv("ALEXA_BACKEND_TOKEN", "")
ALEXA_SKILL_ID = os.getenv("ALEXA_SKILL_ID", "")
MAX_TEXT_LENGTH = 1500
MAX_HISTORY_MESSAGES = 8
MAX_LOG_BODY_BYTES = 128 * 1024
HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
SENSITIVE_KEYS = {
    "userid",
    "accesstoken",
    "apiaccesstoken",
    "deviceid",
}


def _autenticar(request):
    received_token = request.headers.get("X-Alexa-Token", "")

    if not ALEXA_BACKEND_TOKEN:
        return JsonResponse(
            {"error": "ALEXA_BACKEND_TOKEN não configurado"},
            status=503,
        )

    if not hmac.compare_digest(received_token, ALEXA_BACKEND_TOKEN):
        return JsonResponse({"error": "Não autorizado"}, status=401)

    return None


def _carregar_json(request):
    try:
        return json.loads(request.body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({"error": "JSON inválido"}, status=400)


def _texto(value, max_length=MAX_TEXT_LENGTH):
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _sanitizar_json(value, depth=0):
    """Remove identificadores e tokens antes de persistir metadados."""
    if depth > 10:
        return None

    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                continue
            clean[key_text] = _sanitizar_json(item, depth + 1)
        return clean

    if isinstance(value, list):
        return [_sanitizar_json(item, depth + 1) for item in value[:100]]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


def _normalizar_user_hash(body):
    supplied_hash = _texto(body.get("user_id_hash"), 64)
    if HASH_PATTERN.fullmatch(supplied_hash):
        return supplied_hash.lower()

    raw_user_id = _texto(body.get("user_id"), 2000)
    if not raw_user_id:
        return ""

    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        raw_user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


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
    auth_error = _autenticar(request)
    if auth_error:
        return auth_error

    body, json_error = _carregar_json(request)
    if json_error:
        return json_error

    text = body.get("text", "")

    if not isinstance(text, str) or not text.strip():
        return JsonResponse(
            {"error": "O campo text é obrigatório"},
            status=400,
        )

    text = text.strip()[:MAX_TEXT_LENGTH]
    history = _limpar_historico(body.get("history", []))

    try:
        # Importação tardia: o endpoint de logs não precisa carregar Whisper/Groq.
        from .pipeline import gerar_resposta

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


@csrf_exempt
@require_POST
def alexa_interaction(request):
    auth_error = _autenticar(request)
    if auth_error:
        return auth_error

    if len(request.body) > MAX_LOG_BODY_BYTES:
        return JsonResponse({"error": "Payload muito grande"}, status=413)

    body, json_error = _carregar_json(request)
    if json_error:
        return json_error

    if not isinstance(body, dict):
        return JsonResponse({"error": "O corpo deve ser um objeto JSON"}, status=400)

    request_data = body.get("request_data", {})
    if not isinstance(request_data, dict):
        request_data = {}

    request_id = _texto(
        body.get("request_id") or request_data.get("requestId"),
        255,
    )
    session_id = _texto(body.get("session_id"), 255)
    request_type = _texto(
        body.get("request_type") or request_data.get("type"),
        80,
    )

    if not request_id:
        return JsonResponse({"error": "request_id é obrigatório"}, status=400)
    if not session_id:
        return JsonResponse({"error": "session_id é obrigatório"}, status=400)
    if not request_type:
        return JsonResponse({"error": "request_type é obrigatório"}, status=400)

    application_id = _texto(body.get("application_id"), 255)
    if ALEXA_SKILL_ID and application_id != ALEXA_SKILL_ID:
        return JsonResponse({"error": "Skill não autorizada"}, status=403)

    intent_data = request_data.get("intent", {})
    if not isinstance(intent_data, dict):
        intent_data = {}

    intent_name = _texto(
        body.get("intent_name") or intent_data.get("name"),
        150,
    )
    locale = _texto(body.get("locale") or request_data.get("locale"), 20)
    user_text = _texto(body.get("user_text"))
    assistant_text = _texto(body.get("assistant_text"))
    session_ended_reason = _texto(
        body.get("session_ended_reason") or request_data.get("reason"),
        80,
    )

    slots = body.get("slots", {})
    if not isinstance(slots, dict):
        slots = {}

    user_id_hash = _normalizar_user_hash(body)
    clean_slots = _sanitizar_json(slots)
    clean_request_data = _sanitizar_json(request_data)

    with transaction.atomic():
        existing_interaction = (
            InteracaoAlexa.objects.select_related("conversa")
            .filter(request_id=request_id)
            .first()
        )
        if existing_interaction:
            return JsonResponse(
                {
                    "ok": True,
                    "created": False,
                    "conversation_id": existing_interaction.conversa_id,
                    "interaction_id": existing_interaction.id,
                }
            )

        conversa, _ = Conversa.objects.get_or_create(
            alexa_session_id=session_id,
            defaults={
                "perfil": Perfil.obter_ou_criar(),
                "origem": Conversa.Origem.ALEXA,
            },
        )

        fields_to_update = []
        if conversa.origem != Conversa.Origem.ALEXA:
            conversa.origem = Conversa.Origem.ALEXA
            fields_to_update.append("origem")

        if request_type == "SessionEndedRequest" and not conversa.finalizada_em:
            conversa.finalizada_em = timezone.now()
            fields_to_update.append("finalizada_em")

        if fields_to_update:
            conversa.save(update_fields=fields_to_update)

        interaction = InteracaoAlexa.objects.create(
            conversa=conversa,
            request_id=request_id,
            request_type=request_type,
            intent_name=intent_name,
            locale=locale,
            application_id=application_id,
            user_id_hash=user_id_hash,
            user_text=user_text,
            assistant_text=assistant_text,
            slots=clean_slots,
            request_data=clean_request_data,
            session_ended_reason=session_ended_reason,
        )

        if user_text:
            Mensagem.objects.create(
                conversa=conversa,
                autor="usuario",
                texto=user_text,
            )

        if assistant_text:
            Mensagem.objects.create(
                conversa=conversa,
                autor="assistente",
                texto=assistant_text,
            )

    return JsonResponse(
        {
            "ok": True,
            "created": True,
            "conversation_id": conversa.id,
            "interaction_id": interaction.id,
        },
        status=201,
    )
