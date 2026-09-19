import json
import os
import smtplib
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default as email_default_policy
from http.server import BaseHTTPRequestHandler


RECIPIENT_EMAIL = "mayada2678@gmail.com"
MAX_UPLOAD_BYTES = 10_000_000


def parse_multipart(content_type: str, body: bytes) -> dict:
    """Parst multipart/form-data ohne das entfernte `cgi`-Modul zu benötigen."""
    header = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
    message = BytesParser(policy=email_default_policy).parsebytes(header + body)

    fields = {}
    if not message.is_multipart():
        return fields

    for part in message.iter_parts():
        if "name=" not in (part.get("Content-Disposition") or ""):
            continue

        name = part.get_param("name", header="Content-Disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""

        if filename:
            fields[name] = {
                "filename": filename,
                "content": payload,
                "content_type": part.get_content_type(),
            }
        else:
            fields[name] = payload.decode("utf-8", errors="replace")

    return fields


def send_project_email(filename: str, content: bytes, content_type: str) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_app_password:
        raise RuntimeError("Der E-Mail-Versand ist auf dem Server nicht konfiguriert.")

    message = EmailMessage()
    message["Subject"] = "Neues Testprojekt über die Portfolio-Website"
    message["From"] = gmail_user
    message["To"] = RECIPIENT_EMAIL
    message.set_content(
        "Ein Besucher hat über die Portfolio-Website ein Testprojekt hochgeladen.\n\n"
        f"Dateiname: {filename}\n\n"
        "Die Datei ist an diese E-Mail angehängt."
    )

    maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
    message.add_attachment(
        content,
        maintype=maintype or "application",
        subtype=subtype or "octet-stream",
        filename=filename or "testprojekt",
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(gmail_user, gmail_app_password)
        smtp.send_message(message)


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
            if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
                self.send_json(413, {"error": "Die Datei ist zu groß (max. 10 MB) oder leer."})
                return

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_json(400, {"error": "Ungültiges Anfrageformat."})
                return

            body = self.rfile.read(content_length)
            fields = parse_multipart(content_type, body)
            file_field = fields.get("file")

            if not isinstance(file_field, dict) or not file_field.get("content"):
                self.send_json(400, {"error": "Bitte wählen Sie zuerst eine Datei aus."})
                return

            send_project_email(
                file_field.get("filename") or "testprojekt",
                file_field["content"],
                file_field.get("content_type", "application/octet-stream"),
            )

            self.send_json(200, {"ok": True})
        except RuntimeError as error:
            self.send_json(500, {"error": str(error)})
        except (ValueError, TypeError):
            self.send_json(400, {"error": "Die Anfrage konnte nicht gelesen werden."})
        except Exception:
            self.send_json(500, {"error": "Die Datei konnte nicht gesendet werden. Bitte versuchen Sie es erneut."})
