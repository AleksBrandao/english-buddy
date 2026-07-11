from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async

from . import evaluators
from .consumers import TalkConsumer
from .lesson_orchestrator import LessonStage, LessonTransitionError
from .models import AvaliacaoSessao


class FeedbackTalkConsumer(TalkConsumer):
    """TalkConsumer with automatic first-attempt feedback.

    Keeping this integration in a subclass limits the change surface of the
    existing voice pipeline while the guided lesson flow is still evolving.
    """

    async def _command_finish_attempt(self, payload):
        lesson = self._require_active_lesson()
        event = lesson.finish_current_attempt(
            force=bool(payload.get("force", False))
        )
        await self._sincronizar_sessao_treino()
        await self._send_json(event)

        if lesson.state.stage == LessonStage.FIRST_FEEDBACK:
            await self._generate_first_feedback_and_continue()

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
            if lesson.state.stage == LessonStage.FIRST_FEEDBACK:
                await self._generate_first_feedback_and_continue()
            return

        next_question = event.get("next_question")
        if next_question:
            await self._persistir_mensagem("assistente", next_question)
            await self._send_text_and_audio(
                next_question,
                mode="guided_lesson",
            )

    async def _generate_first_feedback_and_continue(self):
        lesson = self._require_active_lesson()
        if lesson.state.stage != LessonStage.FIRST_FEEDBACK:
            raise LessonTransitionError(
                "First-attempt feedback can only be generated during first_feedback."
            )

        await self._send_json(
            {
                "type": "feedback_generating",
                "stage": lesson.state.stage.value,
            }
        )

        feedback, latency = await sync_to_async(
            evaluators.evaluate_first_attempt,
            thread_sensitive=False,
        )(
            list(lesson.state.first_attempt),
            lesson.scenario.target_phrases,
            lesson.scenario.objective,
            lesson.scenario.level,
        )

        feedback_event = lesson.set_intermediate_feedback(feedback)
        await database_sync_to_async(self._save_first_evaluation)(feedback)
        await self._sincronizar_sessao_treino()
        await self._send_json(
            {
                **feedback_event,
                "latency_ms": round(latency * 1000),
            }
        )

        second_attempt_event = lesson.start_second_attempt()
        await self._sincronizar_sessao_treino()
        await self._send_json(second_attempt_event)

        question = second_attempt_event["question"]
        combined_text = f"{feedback['spoken_feedback']} {question}"
        await self._persistir_mensagem("assistente", combined_text)
        await self._send_text_and_audio(
            combined_text,
            mode="guided_feedback",
            extra={"feedback": feedback},
        )

    def _save_first_evaluation(self, feedback):
        AvaliacaoSessao.objects.update_or_create(
            sessao=self.sessao_treino,
            tipo=AvaliacaoSessao.Tipo.PRIMEIRA_TENTATIVA,
            defaults={"dados": feedback},
        )
