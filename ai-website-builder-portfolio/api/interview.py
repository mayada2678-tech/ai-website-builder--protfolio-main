import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from openai import OpenAI
from pypdf import PdfReader


MODEL = "gpt-4o-mini"
RESUME_PATH = Path(__file__).resolve().parent.parent / "lebenslauf_mayada_esmail.pdf"
MUSTERANTWORTEN_PATH = (
    Path(__file__).resolve().parent.parent / "interview_musterantworten.md"
)
_resume_text = None
_musterantworten_text = None


def get_resume_text() -> str:
    global _resume_text

    if _resume_text is None:
        reader = PdfReader(RESUME_PATH)
        _resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    return _resume_text


def get_musterantworten_text() -> str:
    """Liest Mayadas eigene Musterantworten, falls vorhanden."""
    global _musterantworten_text

    if _musterantworten_text is None:
        if MUSTERANTWORTEN_PATH.is_file():
            _musterantworten_text = MUSTERANTWORTEN_PATH.read_text(encoding="utf-8")
        else:
            _musterantworten_text = ""

    return _musterantworten_text


def answer_question(question: str, history: list[dict]) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Die Interview-Konfiguration ist unvollständig.")

    clean_history = [
        {"role": item["role"], "content": item["content"][:1000]}
        for item in history[-8:]
        if item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
    ]

    musterantworten = get_musterantworten_text()
    musterantworten_block = (
        f"\n\nEIGENE MUSTERANTWORTEN VON MAYADA (bevorzugt verwenden, sinngemäß "
        f"in der Sprache der Frage wiedergeben):\n{musterantworten}"
        if musterantworten.strip()
        else ""
    )

    response = OpenAI(api_key=api_key).chat.completions.create(
        model=MODEL,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": f"""
Du bist ein KI-gestützter Interview-Avatar auf der Bewerbungswebsite von Mayada Esmail.
Eine Recruiterin oder ein Recruiter stellt dir eine Frage, so als würde sie/er Mayada
in einem Vorstellungsgespräch befragen.

Antworte IN DER ICH-FORM, so wie Mayada selbst antworten würde: freundlich,
professionell, konkret, ohne zu übertreiben.

Stütze dich ausschließlich auf den Lebenslauf und die Musterantworten unten.
Erfinde keine Fakten, Firmen, Projekte, Zahlen, Gehaltsvorstellungen oder
Verfügbarkeiten, die dort nicht stehen.

Wenn eine Frage damit nicht beantwortet werden kann, sag ehrlich, dass du dazu
keine gesicherte Angabe machen kannst, und schlage vor, Mayada direkt zu
kontaktieren.

Antworte immer in der Sprache der Frage (z. B. Deutsch, Englisch, Arabisch
oder Kurdisch), auch wenn der Lebenslauf nur auf Deutsch vorliegt -- übersetze
und formuliere frei, ohne den Inhalt zu verändern.

Nenne keine privaten Kontakt-, Adress- oder sonstigen sensiblen Daten, die
nicht ohnehin öffentlich auf der Website stehen.

Halte Antworten auf 3-6 Sätze, außer es wird ausdrücklich mehr verlangt.

LEBENSLAUF:
{get_resume_text()}
{musterantworten_block}
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
            self.send_json(500, {"error": "Der Interview-Avatar ist momentan nicht erreichbar."})
