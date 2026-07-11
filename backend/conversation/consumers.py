import json
import os
import uuid

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from . import pipeline
from .lesson_orchestrator import (
    LessonOrchestrator,
    LessonStage,
    LessonTransitionError,
)
from .models import Conversa, Mensagem, Perfil, SessaoTreino
from .scenarios import get_scenario


TEMP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "temp_audio",
)
os.makedirs(TEMP_DIR, exist_ok=True)


class TalkConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        self.perfil = await database_sync_to_async(Perfil.obter_ou_criar)()
        self.conversa = await database_sync_to_async(Conversa.objects.create)(
            perfil=self.perfil
        )
        self.historico = await database_sync_to_async(
            self._carregar_historico_recente
        )()
        self.falas_usuario = []
        self.velocidade = self.perfil.velocidade_preferida
        self.frase_alvo = None

        self.modo = "free"
        self.lesson = None
        self.sessao_treino = None

        await self._send_json(
            {
                "type": "connection_ready",
                "mode": self.modo,
                "available_commands": [
                    "start_lesson",
                    "continue_lesson",
                    "finish_attempt",
                    "lesson_status",
                    "finish_lesson",
                    "start_free_conversation",
                ],
            }
        )
        print(
            "[consumer] Cliente conectado "
            f"(perfil nível: {self.perfil.nivel_atual})"
        )

    def _carregar_historico_recente(self, limite=10):
        """Carrega somente mensagens de conversas livres anteriores."""
        mensagens = (
            Mensagem.objects.filter(
                conversa__perfil=self.perfil,
                conversa__sessao_treino__isnull=True,
            )
            .exclude(conversa=self.conversa)
            .order_by("-criado_em")[:limite]
        )
        historico = []
        for mensagem in reversed(list(mensagens)):
            role = "user" if mensagem.autor == "usuario" else "assistant"
            historico.append({"role": role, "content": mensagem.texto})
        return historico

    async def disconnect(self, close_code):
        await database_sync_to_async(self._finalizar_conversa_atual)()
        if self.sessao_treino and self.lesson:
            await self._sincronizar_sessao_treino()
        print("[consumer] Cliente desconectado")

    async def receive(self, bytes_data=None, text_data=None):
        if text_data is not None:
            await self._receive_command(text_data)
            return

        if bytes_data is not None:
            await self._receive_audio(bytes_data)
            return

        await self._send_error(
            "empty_message",
            "The WebSocket message did not contain text or audio.",
        )

    async def _receive_command(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error(
                "invalid_json",
                "Text WebSocket messages must contain valid JSON.",
            )
            return

        if not isinstance(payload, dict):
            await self._send_error(
                "invalid_command",
                "The WebSocket command must be a JSON object.",
            )
            return

        command = payload.get("type")
        handlers = {
            "start_lesson": self._command_start_lesson,
            "continue_lesson": self._command_continue_lesson,
            "finish_attempt": self._command_finish_attempt,
            "lesson_status": self._command_lesson_status,
            "finish_lesson": self._command_finish_lesson,
            "start_free_conversation": self._command_start_free_conversation,
        }
        handler = handlers.get(command)
        if not handler:
            await self._send_error(
                "unknown_command",
                f"Unknown WebSocket command: {command!r}.",
            )
            return

        try:
            await handler(payload)
        except (LessonTransitionError, ValueError) as exc:
            await self._send_error(
                "invalid_lesson_transition",
                str(exc),
            )

    async def _command_start_lesson(self, payload):
        if self.lesson and self.lesson.state.stage != LessonStage.COMPLETED:
            raise LessonTransitionError("A guided lesson is already active.")

        scenario = get_scenario(
            payload.get("scenario_id", "daily-routine-01")
        )
        await database_sync_to_async(
            self._preparar_conversa_para_nova_atividade
        )()

        self.lesson = LessonOrchestrator(scenario=scenario)
        self.sessao_treino = await database_sync_to_async(
            SessaoTreino.objects.create
        )(
            perfil=self.perfil,
            conversa=self.conversa,
            scenario_id=scenario.scenario_id,
            etapa_atual=self.lesson.state.stage.value,
        )
        self.modo = "lesson"
        self.frase_alvo = None

        event = self.lesson.start()
        await self._sincronizar_sessao_treino()
        await self._send_json(event)

    async def _command_continue_lesson(self, payload):
        lesson = self._require_active_lesson()
        event = lesson.continue_lesson()
        await self._sincronizar_sessao_treino()
        await self._send_json(event)

        question = event.get("question")
        if question:
            await self._persistir_mensagem("assistente", question)
            await self._send_text_and_audio(
                question,
                mode="guided_lesson",
            )

    async def _command_finish_attempt(self, payload):
        lesson = self._require_active_lesson()
        event = lesson.finish_current_attempt(
            force=bool(payload.get("force", False))
        )
        await self._sincronizar_sessao_treino()
        await self._send_json(event)

    async def _command_lesson_status(self, payload):
        lesson = self._require_active_lesson()
        await self._send_json(
            {
                "type": "lesson_status",
                "mode": self.modo,
                **lesson.snapshot(),
            }
        )

    async def _command_finish_lesson(self, payload):
        lesson = self._require_active_lesson()
        previous_stage = lesson.state.stage
        lesson.state.stage = LessonStage.COMPLETED
        await self._sincronizar_sessao_treino()

        await self._send_json(
            {
                "type": "lesson_completed",
                "stage": LessonStage.COMPLETED.value,
                "scenario_id": lesson.scenario.scenario_id,
                "reason": payload.get("reason", "finished_by_user"),
                "previous_stage": previous_stage.value,
            }
        )

    async def _command_start_free_conversation(self, payload):
        if self.lesson and self.lesson.state.stage != LessonStage.COMPLETED:
            if not payload.get("finish_active_lesson", False):
                raise LessonTransitionError(
                    "Finish the active lesson before returning to "
                    "free conversation."
                )
            self.lesson.state.stage = LessonStage.COMPLETED
            await self._sincronizar_sessao_treino()

        await database_sync_to_async(
            self._preparar_conversa_para_nova_atividade
        )()
        self.historico = await database_sync_to_async(
            self._carregar_historico_recente
        )()
        self.falas_usuario = []
        self.frase_alvo = None
        self.lesson = None
        self.sessao_treino = None
        self.modo = "free"

        await self._send_json({"type": "mode_changed", "mode": self.modo})

    async def _receive_audio(self, bytes_data):
        file_id = uuid.uuid4().hex[:8]
        caminho_entrada = os.path.join(
            TEMP_DIR,
            f"entrada_{file_id}.webm",
        )

        try:
            with open(caminho_entrada, "wb") as audio_file:
                audio_file.write(bytes_data)

            texto_usuario, lat_stt, idioma = await sync_to_async(
                pipeline.transcrever,
                thread_sensitive=False,
            )(caminho_entrada)

            await self._send_json(
                {
                    "type": "transcription",
                    "text": texto_usuario,
                    "latency_ms": round(lat_stt * 1000),
                    "idioma": idioma,
                    "mode": self.modo,
                }
            )

            if not texto_usuario:
                return

            if await self._handle_pronunciation_mode(texto_usuario, idioma):
                return

            if self.modo == "lesson":
                await self._handle_lesson_utterance(texto_usuario)
                return

            await self._handle_free_conversation(texto_usuario)
        except LessonTransitionError as exc:
            await self._send_error(
                "invalid_lesson_transition",
                str(exc),
            )
        finally:
            self._remove_file(caminho_entrada)

    async def _handle_pronunciation_mode(self, texto_usuario, idioma):
        if self.frase_alvo:
            acertou, similaridade = pipeline.avaliar_tentativa_pronuncia(
                texto_usuario,
                self.frase_alvo,
            )
            if acertou:
                resposta_texto = "Perfect! That's exactly right. Well done!"
                self.frase_alvo = None
            else:
                resposta_texto = (
                    "Almost! Try again, listen carefully: "
                    f'"{self.frase_alvo}"'
                )

            await self._send_text_and_audio(
                resposta_texto,
                mode="pratica_pronuncia",
                extra={"similaridade": round(similaridade, 2)},
            )
            return True

        if pipeline.pedido_ajuda_em_portugues(texto_usuario, idioma):
            self.frase_alvo = await sync_to_async(
                pipeline.extrair_frase_alvo,
                thread_sensitive=False,
            )(texto_usuario)
            resposta_texto = (
                f'Sure! Try saying: "{self.frase_alvo}". '
                "Listen and repeat it."
            )
            await self._send_text_and_audio(
                resposta_texto,
                mode="pratica_pronuncia",
                extra={"frase_alvo": self.frase_alvo},
            )
            return True

        return False

    async def _handle_lesson_utterance(self, texto_usuario):
        lesson = self._require_active_lesson()
        if lesson.state.stage not in {
            LessonStage.FIRST_ATTEMPT,
            LessonStage.SECOND_ATTEMPT,
        }:
            raise LessonTransitionError(
                "Audio answers are accepted only during a lesson attempt."
            )

        await self._persistir_mensagem("usuario", texto_usuario)
        event = lesson.register_user_utterance(texto_usuario)
        await self._sincronizar_sessao_treino()
        await self._send_json(event)

        transition = event.get("transition")
        if transition:
            await self._send_json(transition)
            return

        next_question = event.get("next_question")
        if next_question:
            await self._persistir_mensagem("assistente", next_question)
            await self._send_text_and_audio(
                next_question,
                mode="guided_lesson",
            )

    async def _handle_free_conversation(self, texto_usuario):
        self.falas_usuario.append(texto_usuario)
        nivel_estimado = pipeline.estimar_nivel(
            self.falas_usuario,
            self.perfil.nivel_atual,
        )

        if len(self.falas_usuario) == 1:
            self.velocidade = pipeline.velocidade_base_por_nivel(
                nivel_estimado
            )
        self.velocidade = pipeline.ajustar_velocidade(
            texto_usuario,
            self.velocidade,
        )

        resposta_texto, lat_llm = await sync_to_async(
            pipeline.gerar_resposta,
            thread_sensitive=False,
        )(
            texto_usuario,
            self.historico,
            nivel_estimado,
            self.perfil.referencia_nivel,
        )

        self.historico.append({"role": "user", "content": texto_usuario})
        self.historico.append(
            {"role": "assistant", "content": resposta_texto}
        )

        await self._persistir_mensagem("usuario", texto_usuario)
        await self._persistir_mensagem("assistente", resposta_texto)
        await database_sync_to_async(
            self._atualizar_preferencias_perfil
        )(nivel_estimado)

        await self._send_text_and_audio(
            resposta_texto,
            mode="free",
            latency_ms=round(lat_llm * 1000),
            extra={
                "nivel_estimado": nivel_estimado,
                "velocidade": self.velocidade,
            },
        )

    async def _send_text_and_audio(
        self,
        text,
        mode,
        latency_ms=None,
        extra=None,
    ):
        payload = {
            "type": "response_text",
            "text": text,
            "modo": mode,
        }
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if extra:
            payload.update(extra)
        await self._send_json(payload)

        output_id = uuid.uuid4().hex[:8]
        caminho_saida = os.path.join(
            TEMP_DIR,
            f"resposta_{output_id}.wav",
        )
        try:
            _, lat_tts = await sync_to_async(
                pipeline.falar,
                thread_sensitive=False,
            )(
                text,
                caminho_saida,
                self.velocidade,
            )
            with open(caminho_saida, "rb") as audio_file:
                await self.send(bytes_data=audio_file.read())
            await self._send_json(
                {
                    "type": "response_audio_done",
                    "latency_ms": round(lat_tts * 1000),
                    "modo": mode,
                }
            )
        finally:
            self._remove_file(caminho_saida)

    def _require_active_lesson(self):
        if not self.lesson or not self.sessao_treino:
            raise LessonTransitionError(
                "There is no active guided lesson."
            )
        return self.lesson

    async def _sincronizar_sessao_treino(self):
        if not self.sessao_treino or not self.lesson:
            return
        await database_sync_to_async(self._save_training_session)()

    def _save_training_session(self):
        self.sessao_treino.etapa_atual = self.lesson.state.stage.value
        self.sessao_treino.primeira_tentativa = list(
            self.lesson.state.first_attempt
        )
        self.sessao_treino.segunda_tentativa = list(
            self.lesson.state.second_attempt
        )
        update_fields = [
            "etapa_atual",
            "primeira_tentativa",
            "segunda_tentativa",
        ]
        if self.lesson.state.stage == LessonStage.COMPLETED:
            self.sessao_treino.finalizada_em = (
                self.sessao_treino.finalizada_em or timezone.now()
            )
            update_fields.append("finalizada_em")
        self.sessao_treino.save(update_fields=update_fields)

    async def _persistir_mensagem(self, autor, texto):
        await database_sync_to_async(Mensagem.objects.create)(
            conversa=self.conversa,
            autor=autor,
            texto=texto,
        )

    def _atualizar_preferencias_perfil(self, nivel_estimado):
        self.perfil.nivel_atual = nivel_estimado
        self.perfil.velocidade_preferida = self.velocidade
        self.perfil.save(
            update_fields=[
                "nivel_atual",
                "velocidade_preferida",
                "atualizado_em",
            ]
        )

    def _preparar_conversa_para_nova_atividade(self):
        has_content = self.conversa.mensagens.exists()
        has_lesson = SessaoTreino.objects.filter(
            conversa=self.conversa
        ).exists()
        if not has_content and not has_lesson:
            return

        self._finalizar_conversa_atual()
        self.conversa = Conversa.objects.create(perfil=self.perfil)

    def _finalizar_conversa_atual(self):
        if self.conversa.finalizada_em is None:
            self.conversa.finalizada_em = timezone.now()
            self.conversa.save(update_fields=["finalizada_em"])

    async def _send_json(self, payload):
        await self.send(
            text_data=json.dumps(payload, ensure_ascii=False)
        )

    async def _send_error(self, code, message):
        await self._send_json(
            {
                "type": "lesson_error",
                "code": code,
                "message": message,
                "mode": getattr(self, "modo", "unknown"),
            }
        )

    @staticmethod
    def _remove_file(path):
        if path and os.path.exists(path):
            os.remove(path)
