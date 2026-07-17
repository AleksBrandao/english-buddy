import hashlib
import hmac
import json
import os

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Conversa, InteracaoAlexa, Mensagem, Perfil


def _hash_identifier(value: str) -> str:
    if not value:
        return ""
    salt = os.environ.get("ALEXA_USER_HASH_SALT", "english-buddy")
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def _extract_slots(request_data: dict) -> dict:
    slots = request_data.get("intent", {}).get("slots", {}) or {}
    return {
        name: {
            "value": slot.get("value", ""),
            "confirmationStatus": slot.get("confirmationStatus", "NONE"),
            "resolutions": slot.get("resolutions", {}),
        }
        for name, slot in slots.items()
    }


def _extract_user_text(request_data: dict, payload: dict, slots: dict) -> str:
    explicit_text = payload.get("user_text")
    if isinstance(explicit_text, str) and explicit_text.strip():
        return explicit_text.strip()

    # A Alexa não envia a transcrição completa de toda fala em IntentRequest.
    # Para intents com slot livre, usamos os valores resolvidos como texto útil.
    values = [item.get("value", "").strip() for item in slots.values()]
    return " ".join(value for value in values if value)


def _authorized(request) -> bool:
    configured_key = os.environ.get("ALEXA_LOGGER_API_KEY", "")
    if not configured_key:
        return True
    provided_key = request.headers.get("X-Alexa-Logger-Key", "")
    return hmac.compare_digest(configured_key, provided_key)


@csrf_exempt
def registrar_interacao_alexa(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Método não permitido."}, status=405)

    if not _authorized(request):
        return JsonResponse({"detail": "Credencial inválida."}, status=401)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "JSON inválido."}, status=400)

    envelope = payload.get("alexa_request") or payload.get("request_envelope") or payload
    request_data = envelope.get("request", {})
    session = envelope.get("session", {})
    context = envelope.get("context", {})
    system = context.get("System", {})

    request_id = request_data.get("requestId", "")
    request_type = request_data.get("type", "")
    session_id = session.get("sessionId", "")
    user_id = session.get("user", {}).get("userId") or system.get("user", {}).get("userId", "")
    device_id = system.get("device", {}).get("deviceId", "")

    if not request_id or not request_type:
        return JsonResponse(
            {"detail": "request.requestId e request.type são obrigatórios."},
            status=400,
        )

    intent_name = request_data.get("intent", {}).get("name", "")
    slots = _extract_slots(request_data)
    user_text = _extract_user_text(request_data, payload, slots)
    assistant_text = str(payload.get("assistant_text") or payload.get("response_text") or "").strip()
    user_hash = _hash_identifier(user_id)

    metadata = {
        "application_id": session.get("application", {}).get("applicationId", ""),
        "device_id_hash": _hash_identifier(device_id),
        "new_session": session.get("new"),
        "timestamp": request_data.get("timestamp", ""),
        "reason": request_data.get("reason", ""),
    }

    with transaction.atomic():
        perfil = Perfil.obter_ou_criar()

        conversa = None
        if session_id:
            conversa = Conversa.objects.filter(
                canal="alexa",
                external_session_id=session_id,
            ).first()

        if conversa is None:
            conversa = Conversa.objects.create(
                perfil=perfil,
                canal="alexa",
                external_session_id=session_id or None,
                external_user_hash=user_hash,
            )

        defaults = {
            "conversa": conversa,
            "request_type": request_type,
            "intent_name": intent_name,
            "slots": slots,
            "locale": request_data.get("locale", ""),
            "user_text": user_text,
            "assistant_text": assistant_text,
            "response_should_end_session": payload.get("should_end_session"),
            "status_code": int(payload.get("status_code", 200)),
            "latency_ms": payload.get("latency_ms"),
            "error": str(payload.get("error") or ""),
            "metadata": metadata,
        }
        interaction, created = InteracaoAlexa.objects.update_or_create(
            request_id=request_id,
            defaults=defaults,
        )

        if created:
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

        if request_type == "SessionEndedRequest" and conversa.finalizada_em is None:
            conversa.finalizada_em = timezone.now()
            conversa.save(update_fields=["finalizada_em"])

    return JsonResponse(
        {
            "id": interaction.id,
            "created": created,
            "conversation_id": conversa.id,
            "request_id": interaction.request_id,
        },
        status=201 if created else 200,
    )
