import time
import os
import subprocess
import sounddevice as sd
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
from groq import Groq

from gravar_vad import gravar_com_vad

# ==== CONFIG ====
SAMPLE_RATE = 16000
GROQ_API_KEY = "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"  # troque pela sua key (ou use variável de ambiente)

PIPER_PATH = os.path.join("piper", "piper.exe")
MODEL_PATH = os.path.join("piper", "voices", "en_US-lessac-medium.onnx")

# ==== SETUP (carrega uma vez só) ====
print("Carregando modelo Whisper...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are a friendly English conversation partner.
Keep responses natural, conversational, and not too long (2-3 sentences max).
Respond as if talking to a friend on a walk."""


def transcrever(caminho_audio):
    start = time.time()
    segments, info = whisper_model.transcribe(caminho_audio, language="en")
    texto = " ".join([seg.text for seg in segments]).strip()
    latencia = time.time() - start
    return texto, latencia


def gerar_resposta(texto_usuario):
    start = time.time()
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": texto_usuario}
        ],
        max_tokens=150,
    )
    latencia = time.time() - start
    return response.choices[0].message.content, latencia


def falar(texto, caminho_saida="resposta.wav"):
    start = time.time()
    processo = subprocess.run(
        [PIPER_PATH, "--model", MODEL_PATH, "--output_file", caminho_saida],
        input=texto.encode("utf-8"),
        capture_output=True,
    )
    latencia = time.time() - start
    if processo.returncode != 0:
        print("Erro no Piper:", processo.stderr.decode("utf-8"))
    return caminho_saida, latencia


def tocar_audio(caminho):
    from scipy.io import wavfile
    sample_rate, data = wavfile.read(caminho)
    sd.play(data, sample_rate)
    sd.wait()


if __name__ == "__main__":
    print("=" * 50)
    print("PIPELINE COMPLETO - English Buddy (teste)")
    print("=" * 50)

    # 1. Gravar (com VAD - para automaticamente quando você silenciar)
    caminho_audio = gravar_com_vad("entrada.wav")
    if caminho_audio is None:
        print("Nenhuma fala detectada, encerrando.")
        exit(1)

    # 2. Transcrever
    print("Transcrevendo...")
    texto_usuario, lat_stt = transcrever(caminho_audio)
    print(f"Você disse: {texto_usuario}")

    # 3. Gerar resposta
    print("Pensando na resposta...")
    resposta_texto, lat_llm = gerar_resposta(texto_usuario)
    print(f"Resposta: {resposta_texto}")

    # 4. Falar
    print("Gerando áudio da resposta...")
    caminho_resposta, lat_tts = falar(resposta_texto)

    # 5. Tocar
    print("🔊 Tocando resposta...")
    tocar_audio(caminho_resposta)

    # Resumo
    total = lat_stt + lat_llm + lat_tts
    print("\n" + "=" * 50)
    print("RESUMO DE LATÊNCIA")
    print("=" * 50)
    print(f"STT (Whisper):  {lat_stt:.2f}s")
    print(f"LLM (Groq):     {lat_llm:.2f}s")
    print(f"TTS (Piper):    {lat_tts:.2f}s")
    print(f"TOTAL:          {total:.2f}s")