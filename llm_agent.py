import requests
from typing import Optional, List, Dict
import datetime # Importa el módulo datetime
import json

class LLMAgent:
    def __init__(self,
                 server_ip: str = "http://localhost:11434",
                 model: str = "deepseek-r1:latest",
                 system_prompt: Optional[str] = None,
                 max_interactions: int = 10):
        self.server_url = server_ip.rstrip("/") + "/api/chat"
        self.model = model
        self.max_interactions = max_interactions
        self.history: List[Dict[str, str]] = []
        if system_prompt:
            self.history = [
                {"role": "user",     "content": system_prompt},
                {"role": "assistant","content": "ok"}
            ]

    def chat(self, user_input: str) -> str:
        # Append user message
        self.history.append({"role": "user", "content": user_input})

        # Trim history to respect max_interactions
        sys_part = self.history[:2] if len(self.history) > 1 else []
        rest    = self.history[2:]
        keep    = rest[-2 * self.max_interactions:]
        to_send = sys_part + keep

        # Modificación clave: Cambiar a stream=True
        resp = requests.post(self.server_url, json={
            "model": self.model,
            "messages": to_send,
            "stream": True # Habilitar el modo de stream
        }, stream=True) # Importante: Añadir stream=True aquí también para requests

        resp.raise_for_status()

        full_reply_content = ""
        # Imprimir la marca de tiempo al inicio del stream
        print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ", end="")

        for chunk in resp.iter_content(chunk_size=None):
            if chunk:
                try:
                    # Decodificar el chunk como una línea de texto JSON
                    json_data = chunk.decode('utf-8').strip()
                    if json_data:
                        # Cada chunk puede contener múltiples objetos JSON si es muy grande
                        for line in json_data.splitlines():
                            if line.strip(): # Asegurarse de que la línea no esté vacía
                                data = json.loads(line)
                                if "content" in data["message"]:
                                    content = data["message"]["content"]
                                    full_reply_content += content
                                    print(content, end="", flush=True) # Imprimir el contenido en la terminal
                except json.JSONDecodeError as e:
                    # Manejar casos donde el chunk no es un JSON completo (puede ocurrir con streams)
                    # print(f"Error decodificando JSON: {e} - Chunk: {chunk.decode('utf-8')}")
                    pass # Ignorar chunks incompletos, se procesarán en la siguiente iteración

        print() # Nueva línea al final de la respuesta

        # Append assistant response
        self.history.append({"role": "assistant", "content": full_reply_content})
        return full_reply_content