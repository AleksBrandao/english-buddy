import json
import os
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from . import pipeline
from .models import Perfil, Conversa, Mensagem

# Pasta temporária pra salvar áudios recebidos/gerados durante a conversa
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp_audio")
os.makedirs(TEMP_DIR, exist_ok=True)


class TalkConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        self.perfil = await sync_to_async(Perfil.obter_ou_criar)()
        self.conversa = await sync_to_async(Conversa.objects.create)(perfil=self.perfil)

        # Carrega as últimas mensagens de conversas anteriores, pra dar continuidade
        self.historico = await sync_to_async(self._carregar_historico_recente)()
        self.falas_usuario = []
        self.velocidade = self.perfil.velocidade_preferida
        self.frase_alvo = None
        print(f"[consumer] Cliente conectado (perfil nível: {self.perfil.nivel_atual})")

    def _carregar_historico_recente(self, limite=10):
        """Busca as últimas mensagens de conversas anteriores (não a atual),
        pra dar sensação de continuidade entre sessões."""
        mensagens = (
            Mensagem.objects
            .filter(conversa__perfil=self.perfil)
            .exclude(conversa=self.conversa)
            .order_by("-criado_em")[:limite]
        )
        historico = []
        for m in reversed(list(mensagens)):
            role = "user" if m.autor == "usuario" else "assistant"
            historico.append({"role": role, "content": m.texto})
        return historico

    async def disconnect(self, close_code):
        from django.utils import timezone
        self.conversa.finalizada_em = timezone.now()
        await sync_to_async(self.conversa.save)()
        print("[consumer] Cliente desconectado")

    async def receive(self, bytes_data=None, text_data=None):
        if not bytes_data:
            return

        session_id = uuid.uuid4().hex[:8]
        caminho_entrada = os.path.join(TEMP_DIR, f"entrada_{session_id}.webm")
        caminho_saida = os.path.join(TEMP_DIR, f"resposta_{session_id}.wav")

        # Salva o áudio recebido
        with open(caminho_entrada, "wb") as f:
            f.write(bytes_data)

        # 1. Transcrever (bloqueante -> roda em thread)
        texto_usuario, lat_stt, idioma = await sync_to_async(pipeline.transcrever)(caminho_entrada)

        await self.send(text_data=json.dumps({
            "type": "transcription",
            "text": texto_usuario,
            "latency_ms": round(lat_stt * 1000),
            "idioma": idioma,
        }))

        if not texto_usuario:
            os.remove(caminho_entrada)
            return

        # ==== MODO DE PRÁTICA DE PRONÚNCIA ====

        # Caso A: usuário está tentando repetir uma frase-alvo já dada
        if self.frase_alvo:
            acertou, similaridade = pipeline.avaliar_tentativa_pronuncia(
                texto_usuario, self.frase_alvo
            )

            if acertou:
                resposta_texto = f"Perfect! That's exactly right. Well done!"
                self.frase_alvo = None
            else:
                resposta_texto = (
                    f"Almost! Try again, listen carefully: \"{self.frase_alvo}\""
                )

            _, lat_tts = await sync_to_async(pipeline.falar)(
                resposta_texto, caminho_saida, self.velocidade
            )
            with open(caminho_saida, "rb") as f:
                audio_bytes = f.read()

            await self.send(text_data=json.dumps({
                "type": "response_text",
                "text": resposta_texto,
                "similaridade": round(similaridade, 2),
                "modo": "pratica_pronuncia",
            }))
            await self.send(bytes_data=audio_bytes)
            await self.send(text_data=json.dumps({"type": "response_audio_done", "latency_ms": round(lat_tts * 1000)}))

            os.remove(caminho_entrada)
            os.remove(caminho_saida)
            return

        # Caso B: usuário está pedindo ajuda em português ("como eu falo...")
        if pipeline.pedido_ajuda_em_portugues(texto_usuario, idioma):
            self.frase_alvo = await sync_to_async(pipeline.extrair_frase_alvo)(texto_usuario)
            resposta_texto = f"Sure! Try saying: \"{self.frase_alvo}\". Listen and repeat it."

            _, lat_tts = await sync_to_async(pipeline.falar)(
                resposta_texto, caminho_saida, self.velocidade
            )
            with open(caminho_saida, "rb") as f:
                audio_bytes = f.read()

            await self.send(text_data=json.dumps({
                "type": "response_text",
                "text": resposta_texto,
                "frase_alvo": self.frase_alvo,
                "modo": "pratica_pronuncia",
            }))
            await self.send(bytes_data=audio_bytes)
            await self.send(text_data=json.dumps({"type": "response_audio_done", "latency_ms": round(lat_tts * 1000)}))

            os.remove(caminho_entrada)
            os.remove(caminho_saida)
            return

        # ==== CONVERSA NORMAL ====

        self.falas_usuario.append(texto_usuario)
        nivel_estimado = pipeline.estimar_nivel(self.falas_usuario, self.perfil.nivel_atual)

        # Ajusta velocidade: começa pela base do nível (só na 1ª fala),
        # depois responde a pedidos explícitos do usuário durante a conversa
        if len(self.falas_usuario) == 1:
            self.velocidade = pipeline.velocidade_base_por_nivel(nivel_estimado)
        self.velocidade = pipeline.ajustar_velocidade(texto_usuario, self.velocidade)

        # 2. Gerar resposta
        resposta_texto, lat_llm = await sync_to_async(pipeline.gerar_resposta)(
            texto_usuario, self.historico, nivel_estimado, self.perfil.referencia_nivel
        )

        # Atualiza histórico (em memória, pra contexto do LLM na sessão atual)
        self.historico.append({"role": "user", "content": texto_usuario})
        self.historico.append({"role": "assistant", "content": resposta_texto})

        # Persiste no banco
        await sync_to_async(Mensagem.objects.create)(
            conversa=self.conversa, autor="usuario", texto=texto_usuario
        )
        await sync_to_async(Mensagem.objects.create)(
            conversa=self.conversa, autor="assistente", texto=resposta_texto
        )
        self.perfil.nivel_atual = nivel_estimado
        self.perfil.velocidade_preferida = self.velocidade
        await sync_to_async(self.perfil.save)()

        await self.send(text_data=json.dumps({
            "type": "response_text",
            "text": resposta_texto,
            "latency_ms": round(lat_llm * 1000),
            "nivel_estimado": nivel_estimado,
            "velocidade": self.velocidade,
        }))

        # 3. Gerar áudio da resposta
        _, lat_tts = await sync_to_async(pipeline.falar)(
            resposta_texto, caminho_saida, self.velocidade
        )

        with open(caminho_saida, "rb") as f:
            audio_bytes = f.read()

        await self.send(bytes_data=audio_bytes)

        await self.send(text_data=json.dumps({
            "type": "response_audio_done",
            "latency_ms": round(lat_tts * 1000),
        }))

        os.remove(caminho_entrada)
        os.remove(caminho_saida)