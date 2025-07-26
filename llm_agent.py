import requests
from typing import Optional, List, Dict
import datetime
import json

class LLMAgent:
    def __init__(self,
                 server_ip: str = "http://localhost:11434",
                 model: str = "deepseek-r1:latest",
                 system_prompt: Optional[str] = None,
                 max_interactions: int = 10,
                 stream: bool = False):
        self.server_url = server_ip.rstrip("/") + "/api/chat"
        self.model = model
        self.max_interactions = max_interactions
        self.stream = stream  # Nuevo parámetro para controlar el streaming
        self.history: List[Dict[str, str]] = []
        if system_prompt:
            self.history = [
                {"role": "user", "content": system_prompt},
                {"role": "assistant", "content": "ok"}
            ]

    def clear_think(self, text):
        if '</think>' in text:
            text = text.split('</think>')[1]
        return text.strip()

    def chat(self, user_input: str, temporal_input: str = "") -> str:
        # Append user message
        self.history.append({"role": "user", "content": user_input + "\n\n" + temporal_input})
        
        # Trim history to respect max_interactions
        sys_part = self.history[:2] if len(self.history) > 1 else []
        rest = self.history[2:]
        keep = rest[-2 * self.max_interactions:]
        to_send = sys_part + keep

        # Usar el parámetro stream de la instancia
        resp = requests.post(self.server_url, json={
            "model": self.model,
            "messages": to_send,
            "stream": self.stream
        }, stream=self.stream)
        
        resp.raise_for_status()
        full_reply_content = ""

        if self.stream:
            # Modo streaming: imprimir mientras llega la respuesta
            print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n", end="")
            
            for chunk in resp.iter_content(chunk_size=None):
                if chunk:
                    try:
                        json_data = chunk.decode('utf-8').strip()
                        if json_data:
                            for line in json_data.splitlines():
                                if line.strip():
                                    data = json.loads(line)
                                    if "content" in data["message"]:
                                        content = data["message"]["content"]
                                        full_reply_content += content
                                        print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        pass
            print()  # Nueva línea al final de la respuesta
        else:
            # Modo no-streaming: obtener respuesta completa sin mostrar
            response_data = resp.json()
            if "message" in response_data and "content" in response_data["message"]:
                full_reply_content = response_data["message"]["content"]

        full_reply_content = self.clear_think(full_reply_content)
        
        # Append assistant response
        self.history[-1] = {"role": "user", "content": user_input}
        self.history.append({"role": "assistant", "content": full_reply_content})
        
        return full_reply_content