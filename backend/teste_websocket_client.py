"""
Cliente de teste: envia um áudio (WAV) via WebSocket pro Consumer do Django
e mostra as respostas recebidas (transcrição, texto da resposta, áudio final).

Uso:
    python teste_websocket_client.py
"""

import asyncio
import json
import websockets

WS_URL = "ws://localhost:8000/ws/talk/"
ARQUIVO_ENTRADA = "teste.wav"          # reusa o áudio que você já gravou antes
ARQUIVO_SAIDA = "resposta_ws.wav"      # onde salvar o áudio de resposta recebido


async def testar():
    print(f"Conectando em {WS_URL} ...")
    async with websockets.connect(WS_URL, max_size=None) as ws:
        print("Conectado! Enviando áudio...")

        with open(ARQUIVO_ENTRADA, "rb") as f:
            audio_bytes = f.read()

        await ws.send(audio_bytes)

        audio_recebido = None

        while True:
            mensagem = await ws.recv()

            if isinstance(mensagem, bytes):
                audio_recebido = mensagem
                print(f"🔊 Áudio de resposta recebido ({len(mensagem)} bytes)")
                continue

            dados = json.loads(mensagem)
            tipo = dados.get("type")

            if tipo == "transcription":
                print(f"📝 Transcrição: {dados['text']}  ({dados['latency_ms']}ms)")
            elif tipo == "response_text":
                print(f"💬 Resposta: {dados['text']}  ({dados['latency_ms']}ms)")
            elif tipo == "response_audio_done":
                print(f"✅ TTS concluído ({dados['latency_ms']}ms)")
                break

        if audio_recebido:
            with open(ARQUIVO_SAIDA, "wb") as f:
                f.write(audio_recebido)
            print(f"Áudio salvo em: {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    asyncio.run(testar())