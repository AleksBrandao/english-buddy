import time
import os
from groq import Groq

# Coloque sua key aqui (ou use variável de ambiente, mais seguro)
client = Groq(api_key="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")

# Simula o texto que viria do Whisper
texto_usuario = "Hi, my name is Alex, and I am testing these speakers."

system_prompt = """You are a friendly English conversation partner. 
Keep responses natural, conversational, and not too long (2-3 sentences max).
Respond as if talking to a friend on a walk."""

start = time.time()

response = client.chat.completions.create(
    model="llama-3.1-8b-instant",  # modelo rápido, bom pra esse caso
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": texto_usuario}
    ],
    max_tokens=150,
)

latency = time.time() - start

print(f"Resposta: {response.choices[0].message.content}")
print(f"Tempo: {latency:.2f}s")