import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from openai import OpenAI
from pypdf import PdfReader


MODEL = "gpt-4o-mini"
RESUME_PATH = Path(__file__).resolve().parent.parent / "lebenslauf_mayada_esmail.pdf"
_resume_text = None


def get_resume_text() -> str:
    global _resume_text

    if _resume_text is None:
        reader = PdfReader(RESUME_PATH)
        _resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    return _resume_text


def answer_question(question: str, history: list[dict]) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Die Chat-Konfiguration ist unvollständig.")

    clean_history = [
        {"role": item["role"], "content": item["content"][:1000]}
        for item in history[-6:]
        if item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
    ]

    response = OpenAI(api_key=api_key).chat.completions.create(
        model=MODEL,
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": f"""
Du bist der professionelle Portfolio-Assistent von Mayada Esmail.
Beantworte Fragen von Interessenten ausschließlich anhand des Lebenslaufs unten.
Sprich nicht als Mayada, sondern zum Beispiel: „Mayada hat Erfahrung in ...“.
Antworte auf Deutsch, kurz, freundlich und übersichtlich. Erfinde keine Details.
Wenn eine Information nicht im Lebenslauf steht oder nicht zum Portfolio passt,
sage das klar und biete an, über eine Kontaktanfrage nachzufragen.

LEBENSLAUF:
{get_resume_text()}
""",
            },
            *clean_history,
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content or "Dazu liegt mir keine Information vor."


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
            if content_length > 10_000:
                self.send_json(413, {"error": "Die Anfrage ist zu lang."})
                return

            data = json.loads(self.rfile.read(content_length) or b"{}")
            question = data.get("question", "").strip()
            if not question or len(question) > 1_000:
                self.send_json(400, {"error": "Bitte stelle eine kurze Frage."})
                return

            history = data.get("history", [])
            if not isinstance(history, list):
                history = []

            self.send_json(200, {"answer": answer_question(question, history)})
        except (json.JSONDecodeError, ValueError):
            self.send_json(400, {"error": "Die Anfrage konnte nicht gelesen werden."})
        except Exception:
            self.send_json(500, {"error": "Der Assistent ist momentan nicht erreichbar."})
