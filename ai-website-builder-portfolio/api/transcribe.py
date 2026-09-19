import io
import json
import os
from http.server import BaseHTTPRequestHandler

from openai import OpenAI


TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
MAX_AUDIO_BYTES = 15_000_000

EXTENSION_BY_CONTENT_TYPE = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
}


def transcribe_audio(audio_bytes: bytes, content_type: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Die Chat-Konfiguration ist unvollständig.")

    extension = EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower(), "webm")

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = f"frage.{extension}"

    response = OpenAI(api_key=api_key).audio.transcriptions.create(
        model=TRANSCRIBE_MODEL,
        file=audio_file,
        language="de",
    )

    return (getattr(response, "text", "") or "").strip()


class handler(BaseHTTPRequestHandler):
    def send_json(self, status_code: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > MAX_AUDIO_BYTES:
                self.send_json(413, {"error": "Die Sprachaufnahme ist zu groß oder leer."})
                return

            content_type = self.headers.get("Content-Type", "audio/webm")
            audio_bytes = self.rfile.read(content_length)

            text = transcribe_audio(audio_bytes, content_type)
            if not text:
                self.send_json(422, {"error": "Es wurde keine Sprache erkannt. Bitte versuchen Sie es erneut."})
                return

            self.send_json(200, {"text": text})
        except ValueError:
            self.send_json(400, {"error": "Die Anfrage konnte nicht gelesen werden."})
        except Exception:
            self.send_json(500, {"error": "Die Sprachverarbeitung ist momentan nicht erreichbar."})
