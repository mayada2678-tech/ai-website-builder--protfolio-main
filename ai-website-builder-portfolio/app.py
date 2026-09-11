import base64
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from openai import OpenAI


st.set_page_config(
    page_title="KI Website Builder Portfolio",
    page_icon="🚀",
    layout="wide",
)

OPENAI_MODEL = "gpt-4o-mini"
FORMSPREE_ENDPOINT = "https://formspree.io/f/mnpqnyvk"
RESUME_FILE_NAME = "lebenslauf_mayada_esmail.pdf"
RESUME_FILE_PATH = Path(__file__).with_name(RESUME_FILE_NAME)
VERCEL_DEPLOYMENTS_URL = (
    "https://api.vercel.com/v13/deployments"
    "?skipAutoDetectionConfirmation=1"
)

try:
    OPENAI_API_KEY = st.secrets["openai_api_key"]
    VERCEL_TOKEN = st.secrets["vercel_token"]
except KeyError:
    st.error(
        "API-Schlüssel fehlen. Hinterlege `openai_api_key` und "
        "`vercel_token` in `.streamlit/secrets.toml`."
    )
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

DEFAULT_STATE = {
    "generated_html": "",
    "html_editor": "",
    "pending_html": "",
    "published_html": "",
    "assets": {},
    "live_url": "",
    "deployment_url": "",
    "deployment_id": "",
    "project_name": "ai-website-builder-portfolio",
    "delete_confirmation": False,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Übernimmt KI- oder HTML-Änderungen vor dem Erstellen der Widgets.
if st.session_state.pending_html:
    st.session_state.generated_html = st.session_state.pending_html
    st.session_state.html_editor = st.session_state.pending_html
    st.session_state.pending_html = ""


def clean_html(html: str) -> str:
    """Entfernt Markdown-Codeblöcke aus einer KI-Antwort."""
    return (
        html.replace("```html", "")
        .replace("```HTML", "")
        .replace("```", "")
        .strip()
    )


def require_complete_html(html: str) -> str:
    """Prüft, ob ein vollständiges HTML-Dokument vorhanden ist."""
    html = clean_html(html)
    html_lower = html.lower()

    if not html:
        raise ValueError("Es wurde kein HTML-Code gefunden.")

    if "<html" not in html_lower and "<!doctype" not in html_lower:
        raise ValueError("Der Inhalt enthält keine vollständige HTML-Website.")

    return html


def queue_html_update(html: str) -> None:
    """Plant ein sicheres HTML-Update für den nächsten Durchlauf."""
    st.session_state.pending_html = require_complete_html(html)


def safe_project_name(name: str) -> str:
    """Erstellt einen gültigen Vercel-Projektnamen."""
    safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return safe_name[:100] or "ai-website-builder-portfolio"


def get_project_name_from_url(live_url: str) -> str:
    """Erstellt einen Projektnamen-Vorschlag aus einer URL."""
    hostname = urlparse(live_url).hostname or ""
    return safe_project_name(hostname.split(".")[0])


def save_uploaded_image(uploaded_file, section_name: str) -> str:
    """Speichert ein Bild als Asset für Vorschau und Vercel-Deployment."""
    if uploaded_file is None:
        raise ValueError("Bitte wähle zuerst ein Bild aus.")

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        extension = ".png"

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    safe_section = re.sub(
        r"[^a-z0-9]+",
        "-",
        section_name.lower(),
    ).strip("-")

    file_name = f"{safe_section or 'bild'}-bild{extension}"

    st.session_state.assets[file_name] = {
        "base64": base64.b64encode(uploaded_file.getvalue()).decode("utf-8"),
        "mime_type": uploaded_file.type or mime_types[extension],
    }

    return file_name


def create_preview_html(html: str) -> str:
    """Ersetzt lokale Bildnamen in der Vorschau durch eingebettete Data-URLs."""
    preview_html = html

    for file_name, asset in st.session_state.assets.items():
        data_url = f"data:{asset['mime_type']};base64,{asset['base64']}"
        preview_html = preview_html.replace(file_name, data_url)

    return add_chatbot_widget(preview_html)


def add_chatbot_widget(html: str) -> str:
        """Fügt den serverseitig angebundenen Portfolio-Chat vor dem Body-Ende ein."""
        if 'id="portfolio-chatbot"' in html:
                return html

        chatbot_html = """
<style>
@keyframes portfolioChatEnter { from { opacity:0; transform:translateY(18px) scale(.98); } to { opacity:1; transform:translateY(0) scale(1); } }
@keyframes portfolioChatPulse { 0%,100% { box-shadow:0 0 0 0 rgba(45,212,191,.38); } 50% { box-shadow:0 0 0 5px rgba(45,212,191,0); } }
#portfolio-chatbot { animation:portfolioChatEnter .55s ease-out both; }
#portfolio-chatbot.chat-collapsed { width:64px !important; }
#portfolio-chatbot.chat-collapsed #portfolio-chat-toggle { width:64px; height:64px; padding:0; border-radius:50%; justify-content:center; }
#portfolio-chatbot.chat-collapsed .portfolio-chat-glow, #portfolio-chatbot.chat-collapsed .portfolio-chat-copy, #portfolio-chatbot.chat-collapsed .portfolio-chat-control { display:none !important; }
#portfolio-chat-tooltip { display:none; }
#portfolio-chatbot.chat-collapsed #portfolio-chat-tooltip { display:block;position:absolute;right:72px;bottom:15px;padding:7px 10px;background:#0b172a;color:#fff;border-radius:5px;box-shadow:0 8px 20px rgba(2,6,23,.2);font-size:12px;font-weight:700;white-space:nowrap; }
#portfolio-chatbot button:focus-visible, #portfolio-chatbot input:focus-visible { outline:3px solid #fbbf24; outline-offset:2px; }
#portfolio-chatbot button:hover { filter:brightness(1.06); }
</style>
<aside id="portfolio-chatbot" style="position:fixed;right:20px;bottom:20px;z-index:9999;width:min(390px,calc(100vw - 28px));font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;letter-spacing:0;">
    <button id="portfolio-chat-toggle" type="button" aria-expanded="true" style="position:relative;display:flex;align-items:center;gap:12px;width:100%;padding:14px 15px;background:#0b172a;color:#fff;border:1px solid #1e3a5f;border-radius:8px;cursor:pointer;text-align:left;box-shadow:0 18px 42px rgba(2,6,23,.32);overflow:hidden;">
        <span class="portfolio-chat-glow" aria-hidden="true" style="position:absolute;inset:0 0 0 auto;width:34%;background:linear-gradient(120deg,transparent,rgba(45,212,191,.14));"></span>
        <span class="portfolio-chat-icon" aria-hidden="true" style="position:relative;display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:#fbbf24;color:#422006;font-weight:850;font-size:20px;box-shadow:inset 0 0 0 3px rgba(255,255,255,.18);">&#128172;</span>
        <span class="portfolio-chat-copy" style="position:relative;flex:1;"><span style="display:block;font-weight:800;font-size:15px;line-height:1.2;">Portfolio-Assistent</span><span style="display:block;margin-top:3px;color:#fef3c7;font-size:11px;line-height:1.25;">Hier kannst du gerne Fragen stellen</span><span style="display:flex;align-items:center;gap:5px;margin-top:4px;color:#cbd5e1;font-size:11px;line-height:1.2;"><i aria-hidden="true" style="display:block;width:7px;height:7px;border-radius:50%;background:#2dd4bf;animation:portfolioChatPulse 2s ease-in-out infinite;"></i>Mayada Esmail · online</span></span>
        <span class="portfolio-chat-control" aria-hidden="true" style="position:relative;color:#fbbf24;font-size:20px;line-height:1;">−</span>
    </button>
    <span id="portfolio-chat-tooltip">Hier kannst du gerne fragen</span>
    <section id="portfolio-chat-panel" style="margin-top:7px;background:#fff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 20px 48px rgba(15,23,42,.24);overflow:hidden;">
        <div style="padding:15px;background:#f8fafc;border-bottom:1px solid #e2e8f0;color:#334155;font-size:13px;line-height:1.5;"><span style="display:block;margin-bottom:3px;color:#0f172a;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;">Ihr direkter Draht zu Mayada</span>Ich beantworte Fragen zu Erfahrung, Kompetenzen und Projekten auf Basis ihres Lebenslaufs.</div>
        <div id="portfolio-chat-messages" aria-live="polite" style="height:230px;overflow-y:auto;padding:15px;background:#fff;color:#1e293b;font-size:14px;line-height:1.55;"><p style="max-width:90%;margin:0;padding:11px 12px;background:#eefbf8;border-left:3px solid #0f766e;border-radius:0 7px 7px 0;">Willkommen. Wobei kann ich Sie zu Mayadas Profil unterstützen?</p></div>
        <div id="portfolio-chat-suggestions" style="display:flex;flex-wrap:wrap;gap:6px;padding:0 13px 13px;background:#fff;"><button type="button" data-question="Welche Kompetenzen bringt Mayada mit?" style="padding:6px 8px;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;font-weight:650;">Kompetenzen</button><button type="button" data-question="Welche Projekterfahrung hat Mayada?" style="padding:6px 8px;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;font-weight:650;">Projekterfahrung</button><button type="button" data-question="Ist Mayada für mein Projekt geeignet?" style="padding:6px 8px;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;font-weight:650;">Projektanfrage</button></div>
        <form id="portfolio-chat-form" style="display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0;background:#fff;">
            <input id="portfolio-chat-input" type="text" aria-label="Frage an den Portfolio-Assistenten" placeholder="Ihre Frage eingeben..." required style="min-width:0;flex:1;padding:10px 11px;color:#0f172a;background:#fff;border:1px solid #94a3b8;border-radius:6px;font:inherit;font-size:14px;outline-offset:2px;">
            <button id="portfolio-chat-submit" type="submit" aria-label="Frage senden" style="padding:10px 14px;background:#0f766e;color:#fff;border:0;border-radius:6px;cursor:pointer;font:inherit;font-size:13px;font-weight:800;box-shadow:0 4px 10px rgba(15,118,110,.22);">Senden</button>
        </form>
    </section>
</aside>
<script>
(() => {
    const toggle = document.getElementById('portfolio-chat-toggle');
    const panel = document.getElementById('portfolio-chat-panel');
    const form = document.getElementById('portfolio-chat-form');
    const input = document.getElementById('portfolio-chat-input');
    const submit = document.getElementById('portfolio-chat-submit');
    const messages = document.getElementById('portfolio-chat-messages');
    const history = [];
    const addMessage = (text, label, isUser = false) => {
        const message = document.createElement('p');
        message.style.cssText = 'max-width:90%;margin:0 0 10px;padding:10px 11px;border-radius:7px;' + (isUser ? 'margin-left:auto;background:#10213d;color:#fff;' : 'background:#f1f5f9;color:#1e293b;');
        message.innerHTML = '<strong>' + label + ':</strong> ';
        message.append(document.createTextNode(text));
        messages.append(message);
        messages.scrollTop = messages.scrollHeight;
    };
    toggle.addEventListener('click', () => {
        panel.hidden = !panel.hidden;
        document.getElementById('portfolio-chatbot').classList.toggle('chat-collapsed', panel.hidden);
        toggle.setAttribute('aria-expanded', String(!panel.hidden));
        if (!panel.hidden) input.focus();
    });
    const sendQuestion = async (question) => {
        if (!question) return;
        addMessage(question, 'Sie', true);
        history.push({role: 'user', content: question});
        input.value = '';
        input.disabled = true;
        submit.disabled = true;
        submit.textContent = 'Sendet...';
        const typing = document.createElement('p');
        typing.id = 'portfolio-chat-typing';
        typing.textContent = 'Assistent schreibt...';
        typing.style.cssText = 'margin:0 0 10px;color:#64748b;font-size:13px;font-style:italic;';
        messages.append(typing);
        messages.scrollTop = messages.scrollHeight;
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({question, history: history.slice(-6)})
            });
            const contentType = response.headers.get('content-type') || '';
            const data = contentType.includes('application/json') ? await response.json() : {};
            if (!response.ok) {
                const message = response.status === 404 || response.status === 405
                    ? 'Der Assistent wird nach der Veröffentlichung auf Vercel aktiv.'
                    : (data.error || 'Der Assistent ist momentan nicht erreichbar.');
                throw new Error(message);
            }
            if (typeof data.answer !== 'string' || !data.answer.trim()) {
                throw new Error('Der Assistent konnte gerade keine Antwort erstellen. Bitte versuchen Sie es erneut.');
            }
            addMessage(data.answer, 'Assistent');
            history.push({role: 'assistant', content: data.answer});
        } catch (error) {
            addMessage(error.message, 'Hinweis');
        } finally {
            typing.remove();
            input.disabled = false;
            submit.disabled = false;
            submit.textContent = 'Senden';
            input.focus();
        }
    };
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        await sendQuestion(input.value.trim());
    });
    document.querySelectorAll('#portfolio-chat-suggestions [data-question]').forEach((button) => {
        button.addEventListener('click', () => sendQuestion(button.dataset.question));
    });
})();
</script>
"""

        return re.sub(r"</body\s*>", chatbot_html + "</body>", html, count=1, flags=re.I)


def ask_ai_for_html(system_instruction: str, user_instruction: str) -> str:
    """Fordert vollständigen HTML-Code von OpenAI an."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.35,
        timeout=60,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_instruction},
        ],
    )

    return response.choices[0].message.content or ""


def generate_website(description: str, image_file) -> None:
    """Erstellt einen neuen Website-Entwurf."""
    image_instruction = ""

    if image_file is not None:
        image_name = save_uploaded_image(image_file, "profil")
        image_instruction = f"""
Nutze dieses Bild professionell im Hero- oder Über-mich-Bereich:
<img src="{image_name}" alt="Profilbild">
"""

    html = ask_ai_for_html(
        system_instruction=f"""
Du bist ein professioneller Webdesigner und Frontend-Entwickler.

Erstelle eine moderne, hochwertige und responsive Single-Page-Website.

Regeln:
- Nutze vollständiges HTML5 und beginne mit <!doctype html>.
- Binde Tailwind CSS mit https://cdn.tailwindcss.com ein.
- Erstelle Navigation, Hero, Über mich, Leistungen, Projekte, Kontakt und Footer.
- Die Website muss mobilfreundlich und professionell aussehen.
- Antworte ausschließlich mit vollständigem HTML.
- Kein Markdown, keine Backticks und keine Erklärung.

Hero-Buttons:
- Ersetze die beiden bestehenden Buttons der Hero-Section vollständig und unverändert durch diesen nativen HTML-Code:
<div style="display: flex; gap: 15px; justify-content: center; margin-top: 25px;">
  
    <!-- Button 1: Scrollt direkt zum Formular nach unten via JavaScript -->
    <button onclick="document.getElementById('contact-form') ? document.getElementById('contact-form').scrollIntoView({{behavior: 'smooth'}}) : window.scrollTo({{top: document.body.scrollHeight, behavior: 'smooth'}});" 
                    style="padding: 12px 24px; background: linear-gradient(to right, #2563eb, #7c3aed); color: white; font-weight: 600; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.2);">
        Projekt anfragen
    </button>

    <!-- Button 2: Öffnet den Lebenslauf direkt über einen absoluten Link -->
    <a href="./lebenslauf_mayada_esmail.pdf" 
         target="_blank" 
         style="padding: 12px 24px; background: #1e293b; color: #f1f5f9; font-weight: 600; border: 1px solid #334155; border-radius: 8px; text-decoration: none; display: inline-block;">
        Lebenslauf ansehen
    </a>

</div>

Kontaktformular:
- Erstelle einen sichtbaren, modernen Kontaktbereich.
- Das Formular muss EXAKT diesen Formspree-Endpunkt verwenden:
    <form id="contact-form" action="{FORMSPREE_ENDPOINT}" method="POST">
- Verwende kein JavaScript oder AJAX zum Absenden.
- Das Formular benötigt sichtbare Labels sowie diese Pflichtfelder:
  <input id="name" type="text" name="name" required>
  <input id="email" type="email" name="email" required>
  <input id="subject" type="text" name="subject" required>
  <textarea id="message" name="message" required></textarea>
- Der Button besitzt type="submit" und lautet „Nachricht senden“.

{image_instruction}
""",
        user_instruction=description,
    )

    queue_html_update(html)


def modify_current_website(change_request: str) -> None:
    """Ändert ausschließlich die angeforderten Bereiche der Website."""
    current_html = st.session_state.generated_html.strip()

    if not current_html:
        raise ValueError("Erstelle oder lade zuerst eine Website.")

    html = ask_ai_for_html(
        system_instruction=f"""
Du bist ein sorgfältiger Frontend-Entwickler.

Bearbeite ausschließlich die angeforderte Änderung in einer bestehenden Website.

Regeln:
- Antworte nur mit vollständigem HTML5, beginnend mit <!doctype html>.
- Kein Markdown, keine Backticks und keine Erklärung.
- Bestehende Texte, Bilder, Links, Bereiche und Styles bleiben erhalten,
  sofern ihre Änderung nicht ausdrücklich verlangt wird.
- Tailwind CSS muss erhalten bleiben.

Hero-Buttons:
- Die Hero-Section muss genau diesen nativen HTML-Code für ihre beiden Buttons enthalten:
<div style="display: flex; gap: 15px; justify-content: center; margin-top: 25px;">
  
    <!-- Button 1: Scrollt direkt zum Formular nach unten via JavaScript -->
    <button onclick="document.getElementById('contact-form') ? document.getElementById('contact-form').scrollIntoView({{behavior: 'smooth'}}) : window.scrollTo({{top: document.body.scrollHeight, behavior: 'smooth'}});" 
                    style="padding: 12px 24px; background: linear-gradient(to right, #2563eb, #7c3aed); color: white; font-weight: 600; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.2);">
        Projekt anfragen
    </button>

    <!-- Button 2: Öffnet den Lebenslauf direkt über einen absoluten Link -->
    <a href="./lebenslauf_mayada_esmail.pdf" 
         target="_blank" 
         style="padding: 12px 24px; background: #1e293b; color: #f1f5f9; font-weight: 600; border: 1px solid #334155; border-radius: 8px; text-decoration: none; display: inline-block;">
        Lebenslauf ansehen
    </a>

</div>

Kontaktformular:
- Ein Kontaktformular muss diesen Formspree-Endpunkt verwenden:
    <form id="contact-form" action="{FORMSPREE_ENDPOINT}" method="POST">
- Das Formular muss die Felder `name`, `email`, `subject` und `message` haben.
- Alle Felder besitzen das Attribut `required`.
- Der Button hat type="submit" und lautet „Nachricht senden“.
- Verwende keinen anderen Formularanbieter und kein JavaScript/AJAX.
- Behalte das Design des Kontaktbereichs bei.
""",
        user_instruction=f"""
AKTUELLER HTML-CODE:
{current_html}

GEWÜNSCHTE ÄNDERUNG:
{change_request}
""",
    )

    queue_html_update(html)


def is_vercel_login_page(response: requests.Response) -> bool:
    """Erkennt Vercel-Login- und Deployment-Schutzseiten."""
    content = response.text.lower()
    url = response.url.lower()

    markers = [
        "vercel.com/login",
        "<title>log in to vercel</title>",
        "continue with github",
        "continue with google",
        "continue with chatgpt",
        "deployment protection",
        "vercel authentication",
    ]

    return any(marker in url or marker in content for marker in markers)


def load_published_website(live_url: str) -> None:
    """Lädt eine öffentliche Website unverändert, ohne KI-Bearbeitung."""
    live_url = live_url.strip()

    if not live_url.startswith(("https://", "http://")):
        live_url = f"https://{live_url}"

    try:
        response = requests.get(
            live_url,
            headers={"User-Agent": "AI-Website-Builder/1.0"},
            timeout=30,
            allow_redirects=True,
        )
    except requests.RequestException as error:
        raise ValueError(
            f"Die Website konnte nicht erreicht werden: {error}"
        ) from error

    if is_vercel_login_page(response):
        raise ValueError(
            "Die Website ist durch Vercel geschützt oder verlangt eine Anmeldung."
        )

    if response.status_code != 200:
        raise ValueError(
            f"Die Website konnte nicht geladen werden. HTTP {response.status_code}."
        )

    html = require_complete_html(response.text)

    st.session_state.assets = {}
    st.session_state.live_url = response.url
    st.session_state.deployment_url = response.url

    # Projektname nicht automatisch aus einer Deployment-URL ableiten.
    # Der richtige Projektname wird im Feld „Vercel-Projektname“ eingegeben.
    st.session_state.published_html = html
    st.session_state.pending_html = html

    # Geladene fremde Seiten dürfen über die App nicht gelöscht werden.
    st.session_state.deployment_id = ""


def get_public_url(deployment: dict) -> str:
    """Ermittelt die öffentliche URL aus einer Vercel-Deployment-Antwort."""
    aliases = deployment.get("alias") or []
    deployment_url = deployment.get("url")

    if aliases:
        return f"https://{aliases[0]}"

    if deployment_url:
        return f"https://{deployment_url}"

    raise ValueError("Vercel hat keine öffentliche Deployment-URL geliefert.")

def delete_published_website() -> None:
    """Löscht nur das letzte Deployment aus der aktuellen Sitzung."""
    deployment_id = st.session_state.deployment_id

    if not deployment_id:
        raise ValueError("Kein Deployment aus dieser Sitzung zum Löschen vorhanden.")

    try:
        response = requests.delete(
            f"https://api.vercel.com/v13/deployments/{deployment_id}",
            headers={"Authorization": f"Bearer {VERCEL_TOKEN}"},
            timeout=60,
        )
    except requests.RequestException as error:
        raise ValueError(f"Vercel konnte nicht erreicht werden: {error}") from error

    if response.status_code not in (200, 202, 204):
        raise ValueError(f"Vercel HTTP {response.status_code}: {response.text}")

    st.session_state.live_url = ""
    st.session_state.deployment_url = ""
    st.session_state.deployment_id = ""
    st.session_state.published_html = ""

    
def publish_website() -> None:
    """Veröffentlicht den aktuellen HTML-Entwurf auf Vercel."""
    html = add_chatbot_widget(require_complete_html(st.session_state.generated_html))
    project_name = safe_project_name(st.session_state.project_name)

    files = [
        {"file": "index.html", "data": html},
        {
            "file": "api/chat.py",
            "data": Path(__file__).with_name("api").joinpath("chat.py").read_text(
                encoding="utf-8"
            ),
        },
        {
            "file": "api/requirements.txt",
            "data": Path(__file__)
            .with_name("api")
            .joinpath("requirements.txt")
            .read_text(encoding="utf-8"),
        },
    ]

    if not RESUME_FILE_PATH.is_file():
        raise ValueError(
            f"Die Lebenslauf-Datei '{RESUME_FILE_NAME}' wurde nicht gefunden."
        )

    files.append(
        {
            "file": RESUME_FILE_NAME,
            "data": base64.b64encode(RESUME_FILE_PATH.read_bytes()).decode("utf-8"),
            "encoding": "base64",
        }
    )

    for file_name, asset in st.session_state.assets.items():
        files.append(
            {
                "file": file_name,
                "data": asset["base64"],
                "encoding": "base64",
            }
        )

    payload = {
        "name": project_name,
        "target": "production",
        "env": {"OPENAI_API_KEY": OPENAI_API_KEY},
        "files": files,
        "projectSettings": {
            "framework": None,
            "buildCommand": None,
            "devCommand": None,
            "installCommand": None,
            "outputDirectory": None,
            "rootDirectory": None,
        },
    }

    try:
        response = requests.post(
            VERCEL_DEPLOYMENTS_URL,
            headers={
                "Authorization": f"Bearer {VERCEL_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
    except requests.RequestException as error:
        raise ValueError(f"Vercel konnte nicht erreicht werden: {error}") from error

    if response.status_code not in (200, 201):
        try:
            details = response.json()
        except ValueError:
            details = response.text

        raise ValueError(f"Vercel HTTP {response.status_code}: {details}")

    try:
        deployment = response.json()
    except ValueError as error:
        raise ValueError(
            "Vercel hat keine gültige JSON-Antwort zurückgegeben."
        ) from error

    deployment_id = deployment.get("id")
    deployment_url = deployment.get("url")

    if not deployment_id or not deployment_url:
        raise ValueError(f"Unvollständige Vercel-Antwort: {deployment}")

    # project_name hier NICHT verändern: Es gehört zum Streamlit-Textfeld.
    st.session_state.live_url = get_public_url(deployment)
    st.session_state.deployment_url = f"https://{deployment_url}"
    st.session_state.deployment_id = deployment_id
    st.session_state.published_html = html


st.title("🚀 KI Website Builder Portfolio")
st.caption("Website erstellen, bearbeiten, prüfen und veröffentlichen.")

new_tab, manage_tab = st.tabs(
    ["✨ Neue Website", "⚙️ Veröffentlichte Website laden"]
)



with new_tab:
    st.subheader("Neuen Website-Entwurf erstellen")

    description = st.text_area(
        "Beschreibung der Website",
        placeholder=(
            "Beispiel: Moderne Website für ein Kosmetikstudio in Berlin "
            "mit Leistungen, Preisen, Team, Galerie und Kontaktformular."
        ),
        height=170,
    )

    initial_image = st.file_uploader(
        "Logo oder Bild hochladen (optional)",
        type=["png", "jpg", "jpeg", "webp"],
        key="initial_image",
    )

    if st.button(
        "✨ Website-Entwurf generieren",
        type="primary",
        use_container_width=True,
    ):
        if not description.strip():
            st.warning("Bitte beschreibe die gewünschte Website.")
        else:
            with st.status("Website wird erstellt ...", expanded=True) as status:
                try:
                    generate_website(description, initial_image)
                    status.update(
                        label="✅ Entwurf wurde erstellt.",
                        state="complete",
                    )
                    st.rerun()
                except Exception as error:
                    status.update(
                        label="❌ Erstellung fehlgeschlagen",
                        state="error",
                    )
                    st.error(str(error))

with manage_tab:
    st.subheader("Öffentliche Website laden")
    st.caption(
        "Das Original wird geladen, ohne HTML oder Design vor dem Bearbeiten zu ändern."
    )

    live_url_input = st.text_input(
        "Öffentlicher Live-Link",
        placeholder="https://deine-website.vercel.app",
        key="manage_live_url",
    )

    if st.button(
        "⚙️ Original-Website laden",
        type="primary",
        use_container_width=True,
    ):
        if not live_url_input.strip():
            st.warning("Bitte gib einen Live-Link ein.")
        else:
            with st.status("Website wird geladen ...", expanded=True) as status:
                try:
                    load_published_website(live_url_input)
                    status.update(
                        label="✅ Original-Website wurde unverändert geladen.",
                        state="complete",
                    )
                    st.rerun()
                except Exception as error:
                    status.update(
                        label="❌ Laden fehlgeschlagen",
                        state="error",
                    )
                    st.error(str(error))

if st.session_state.live_url:
    st.success("Eine veröffentlichte oder geladene Website ist verfügbar.")

    st.link_button(
        "🔗 Geänderte Website öffnen",
        st.session_state.live_url,
        use_container_width=True,
    )

    st.caption(f"Live-Link: {st.session_state.live_url}")

st.divider()
st.header("Live-Vorschau")

if st.session_state.generated_html:
    st.components.v1.html(
        create_preview_html(st.session_state.generated_html),
        height=650,
        scrolling=True,
    )
else:
    st.info(
        "Die Vorschau bleibt sichtbar. Erstelle oder lade zuerst eine Website."
    )

if st.session_state.generated_html:
    st.divider()
    st.header("Website bearbeiten")

    content_tab, design_tab, image_tab, html_tab = st.tabs(
        ["📝 Inhalte", "🎨 Design", "🖼️ Bilder", "💻 HTML-Code"]
    )

    with content_tab:
        section = st.selectbox(
            "Bereich auswählen",
            [
                "Navigation",
                "Hero-Bereich",
                "Über mich",
                "Leistungen",
                "Projekte",
                "Kontakt",
                "Footer",
                "Neuen Bereich hinzufügen",
            ],
        )

        change_request = st.text_area(
            "Gewünschte Änderung",
            placeholder=(
                "Beispiel: Ersetze das Kontaktformular durch das konfigurierte "
                "Formspree-Formular und behalte das aktuelle Design."
            ),
            height=130,
        )

        if st.button("📝 Bereich aktualisieren", use_container_width=True):
            if not change_request.strip():
                st.warning("Bitte beschreibe die gewünschte Änderung.")
            else:
                with st.status("Bereich wird bearbeitet ...", expanded=True) as status:
                    try:
                        modify_current_website(
                            f"Ändere ausschließlich den Bereich „{section}“: "
                            f"{change_request}"
                        )
                        status.update(
                            label="✅ Vorschau wurde aktualisiert.",
                            state="complete",
                        )
                        st.rerun()
                    except Exception as error:
                        status.update(
                            label="❌ Änderung fehlgeschlagen",
                            state="error",
                        )
                        st.error(str(error))

    with design_tab:
        design_request = st.text_area(
            "Design-Änderung",
            placeholder=(
                "Beispiel: Dunkles Premium-Design mit goldenen Akzenten, "
                "runden Karten und größeren Buttons."
            ),
            height=130,
        )

        if st.button("🎨 Design aktualisieren", use_container_width=True):
            if not design_request.strip():
                st.warning("Bitte beschreibe die gewünschte Design-Änderung.")
            else:
                with st.status("Design wird angepasst ...", expanded=True) as status:
                    try:
                        modify_current_website(
                            "Ändere ausschließlich Farben, Layout, Abstände und "
                            "Styling. Texte, Bilder und Struktur bleiben erhalten. "
                            f"Wunsch: {design_request}"
                        )
                        status.update(
                            label="✅ Design wurde aktualisiert.",
                            state="complete",
                        )
                        st.rerun()
                    except Exception as error:
                        status.update(
                            label="❌ Design-Änderung fehlgeschlagen",
                            state="error",
                        )
                        st.error(str(error))

    with image_tab:
        image_section = st.selectbox(
            "Abschnitt für das Bild",
            ["Hero-Bereich", "Über mich", "Leistungen", "Projekte", "Kontakt"],
        )

        image_file = st.file_uploader(
            "Neues Bild hochladen",
            type=["png", "jpg", "jpeg", "webp"],
            key="section_image",
        )

        if st.button("🖼️ Bild aktualisieren", use_container_width=True):
            if image_file is None:
                st.warning("Bitte wähle zuerst ein Bild aus.")
            else:
                with st.status("Bild wird aktualisiert ...", expanded=True) as status:
                    try:
                        image_name = save_uploaded_image(image_file, image_section)

                        modify_current_website(
                            f"""
Ändere ausschließlich das Bild im Bereich „{image_section}“.

Verwende exakt dieses Bild:
<img src="{image_name}" alt="{image_section} Bild">

Alle anderen Inhalte müssen unverändert bleiben.
"""
                        )

                        status.update(
                            label="✅ Bild wurde aktualisiert.",
                            state="complete",
                        )
                        st.rerun()
                    except Exception as error:
                        status.update(
                            label="❌ Bild-Änderung fehlgeschlagen",
                            state="error",
                        )
                        st.error(str(error))

    with html_tab:
        st.text_area(
            "HTML-Quellcode",
            height=620,
            key="html_editor",
        )

        if st.button(
            "👁️ Vorschau aus HTML aktualisieren",
            use_container_width=True,
        ):
            try:
                st.session_state.generated_html = require_complete_html(
                    st.session_state.html_editor
                )
                st.rerun()
            except ValueError as error:
                st.warning(str(error))

        st.download_button(
            "⬇️ HTML herunterladen",
            data=st.session_state.generated_html,
            file_name="website.html",
            mime="text/html",
            use_container_width=True,
        )

    st.divider()
    st.header("Veröffentlichung")

    st.text_input(
        "Vercel-Projektname",
        key="project_name",
        help=(
            "Muss exakt dem Namen des Projekts im Vercel-Dashboard entsprechen. "
            "Dann wird dessen Production-Version aktualisiert."
        ),
    )

    publish_column, delete_column = st.columns(2, gap="large")

    with publish_column:
        if st.button(
            "🚀 Änderungen veröffentlichen",
            type="primary",
            use_container_width=True,
        ):
            with st.status(
                "Website wird auf Vercel veröffentlicht ...",
                expanded=True,
            ) as status:
                try:
                    publish_website()
                    status.update(
                        label="🎉 Änderungen wurden veröffentlicht.",
                        state="complete",
                    )
                    st.rerun()
                except Exception as error:
                    status.update(
                        label="❌ Veröffentlichung fehlgeschlagen",
                        state="error",
                    )
                    st.error("Die Veröffentlichung bei Vercel ist fehlgeschlagen.")
                    st.code(str(error), language="text")

    with delete_column:
        if st.session_state.deployment_id:
            st.checkbox(
                "Ich möchte das letzte Deployment löschen.",
                key="delete_confirmation",
            )

            if st.button(
                "🗑️ Letztes Deployment löschen",
                disabled=not st.session_state.delete_confirmation,
                use_container_width=True,
            ):
                try:
                    delete_published_website()
                    st.success("Deployment wurde gelöscht.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Löschen fehlgeschlagen: {error}")
        else:
            st.info(
                "Extern geladene Websites können über diese App nicht gelöscht werden."
            )