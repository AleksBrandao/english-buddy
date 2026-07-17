import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from .models import Conversa, InteracaoAlexa, Mensagem


class AlexaInteractionEndpointTests(TestCase):
    token = "test-token"
    skill_id = "amzn1.ask.skill.fd2ad6fa-355f-4cf7-b292-8056d442c47b"

    def _payload(self, **overrides):
        payload = {
            "request_id": "amzn1.echo-api.request.001",
            "session_id": "amzn1.echo-api.session.001",
            "application_id": self.skill_id,
            "user_id": "amzn1.ask.account.raw-user-id",
            "request_type": "IntentRequest",
            "intent_name": "ConversationIntent",
            "locale": "en-US",
            "slots": {
                "text": {
                    "value": "I worked today",
                    "confirmationStatus": "NONE",
                }
            },
            "user_text": "I worked today",
            "assistant_text": "That sounds productive. What did you do next?",
            "request_data": {
                "type": "IntentRequest",
                "requestId": "amzn1.echo-api.request.001",
                "locale": "en-US",
                "intent": {
                    "name": "ConversationIntent",
                },
            },
        }
        payload.update(overrides)
        return payload

    def _post(self, payload, token=None, configured_skill_id=""):
        headers = {
            "HTTP_X_ALEXA_TOKEN": self.token if token is None else token,
        }
        with (
            patch(
                "conversation.alexa_views.ALEXA_BACKEND_TOKEN",
                self.token,
            ),
            patch(
                "conversation.alexa_views.ALEXA_SKILL_ID",
                configured_skill_id,
            ),
        ):
            return self.client.post(
                reverse("alexa-interaction"),
                data=json.dumps(payload),
                content_type="application/json",
                **headers,
            )

    def test_rejects_invalid_token(self):
        response = self._post(self._payload(), token="wrong-token")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Conversa.objects.count(), 0)

    def test_creates_conversation_interaction_and_messages(self):
        raw_user_id = "amzn1.ask.account.raw-user-id"
        response = self._post(self._payload(user_id=raw_user_id))

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["created"])

        conversa = Conversa.objects.get()
        self.assertEqual(conversa.origem, Conversa.Origem.ALEXA)
        self.assertEqual(
            conversa.alexa_session_id,
            "amzn1.echo-api.session.001",
        )

        interaction = InteracaoAlexa.objects.get()
        self.assertEqual(interaction.intent_name, "ConversationIntent")
        self.assertEqual(len(interaction.user_id_hash), 64)
        self.assertNotEqual(interaction.user_id_hash, raw_user_id)
        self.assertNotIn(raw_user_id, json.dumps(interaction.request_data))

        messages = list(
            Mensagem.objects.values_list("autor", "texto")
        )
        self.assertEqual(
            messages,
            [
                ("usuario", "I worked today"),
                (
                    "assistente",
                    "That sounds productive. What did you do next?",
                ),
            ],
        )

    def test_groups_requests_by_session_and_ignores_duplicate_request(self):
        first_response = self._post(self._payload())
        self.assertEqual(first_response.status_code, 201)

        second_payload = self._payload(
            request_id="amzn1.echo-api.request.002",
            user_text="Then I went home",
            assistant_text="Nice. What did you do at home?",
            request_data={
                "type": "IntentRequest",
                "requestId": "amzn1.echo-api.request.002",
                "locale": "en-US",
                "intent": {"name": "ConversationIntent"},
            },
        )
        second_response = self._post(second_payload)

        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(Conversa.objects.count(), 1)
        self.assertEqual(InteracaoAlexa.objects.count(), 2)
        self.assertEqual(Mensagem.objects.count(), 4)

        duplicate_response = self._post(second_payload)

        self.assertEqual(duplicate_response.status_code, 200)
        self.assertFalse(duplicate_response.json()["created"])
        self.assertEqual(Conversa.objects.count(), 1)
        self.assertEqual(InteracaoAlexa.objects.count(), 2)
        self.assertEqual(Mensagem.objects.count(), 4)

    def test_session_ended_request_finalizes_conversation(self):
        self._post(
            self._payload(
                request_type="LaunchRequest",
                intent_name="",
                user_text="",
                assistant_text="Welcome to English Buddy.",
                request_data={
                    "type": "LaunchRequest",
                    "requestId": "amzn1.echo-api.request.001",
                    "locale": "en-US",
                },
            )
        )

        end_response = self._post(
            self._payload(
                request_id="amzn1.echo-api.request.003",
                request_type="SessionEndedRequest",
                intent_name="",
                user_text="",
                assistant_text="",
                session_ended_reason="USER_INITIATED",
                request_data={
                    "type": "SessionEndedRequest",
                    "requestId": "amzn1.echo-api.request.003",
                    "reason": "USER_INITIATED",
                    "locale": "en-US",
                },
            )
        )

        self.assertEqual(end_response.status_code, 201)
        conversa = Conversa.objects.get()
        self.assertIsNotNone(conversa.finalizada_em)
        interaction = InteracaoAlexa.objects.get(
            request_type="SessionEndedRequest"
        )
        self.assertEqual(
            interaction.session_ended_reason,
            "USER_INITIATED",
        )

    def test_rejects_another_skill_when_skill_id_is_configured(self):
        response = self._post(
            self._payload(application_id="another-skill"),
            configured_skill_id=self.skill_id,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(InteracaoAlexa.objects.count(), 0)
