import subprocess
import time
import os

PIPER_PATH = os.path.join("piper", "piper.exe")
MODEL_PATH = os.path.join("piper", "voices", "en_US-lessac-medium.onnx")
OUTPUT_PATH = "resposta_tts.wav"

def gerar_fala(texto: str, output_path: str = OUTPUT_PATH) -> float:
    start = time.time()
    
    processo = subprocess.run(
        [PIPER_PATH, "--model", MODEL_PATH, "--output_file", output_path],
        input=texto.encode("utf-8"),
        capture_output=True,
    )
    
    latency = time.time() - start
    
    if processo.returncode != 0:
        print("Erro:", processo.stderr.decode("utf-8"))
    
    return latency

if __name__ == "__main__":
    texto = "Nice to meet you, Alex. They sound good so far, do you want to try a normal conversation and see how well they pick up?"
    
    latency = gerar_fala(texto)
    print(f"Áudio gerado em: {OUTPUT_PATH}")
    print(f"Tempo: {latency:.2f}s")