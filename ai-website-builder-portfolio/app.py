import base64
import hashlib
import json
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
CERTIFICATE_DIR = Path(__file__).with_name("zertifikate")
CERTIFICATE_VIEWER_FILE_NAME = "zertifikate.html"
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


def get_certificate_files() -> list[Path]:
    """Listet alle Zertifikats-PDFs aus dem konfigurierten Ordner auf."""
    if not CERTIFICATE_DIR.is_dir():
        return []

    return sorted(
        (path for path in CERTIFICATE_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.lower(),
    )


def slugify_certificate_filename(stem: str, index: int) -> str:
    """Erstellt einen sicheren Dateinamen für das Deployment."""
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"{index:02d}-{slug or 'zertifikat'}.pdf"


def prettify_certificate_name(stem: str) -> str:
    """Erstellt einen lesbaren Anzeigenamen aus dem Dateinamen."""
    match = re.match(
        r"^Zertifikat[_-]\d+[_-](.+?)[_-]\d{6,8}(?:\s*\(\d+\))?$",
        stem,
        re.IGNORECASE,
    )

    if match:
        course = re.sub(r"[_-]+", " ", match.group(1)).strip()
        return f"{course} – Zertifikat"

    return re.sub(r"[_-]+", " ", stem).strip()


def build_certificate_viewer_html(certificates: list[dict]) -> str:
    """Erstellt eine eigenständige Seite zum Durchblättern aller Zertifikate."""
    certificates_json = json.dumps(certificates, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zertifikate &ndash; Mayada Esmail</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  @keyframes certFadeIn {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:translateY(0); }} }}
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif; }}
  #cert-frame {{ animation: certFadeIn .35s ease both; }}
  .cert-item {{ transition: background-color .2s ease, border-color .2s ease, transform .2s ease; }}
  .cert-item:hover {{ transform: translateX(2px); }}
  .cert-item.active {{ background: linear-gradient(90deg, rgba(37,99,235,.18), rgba(124,58,237,.18)); border-color: #7c3aed; }}
  .cert-nav-btn {{ transition: filter .2s ease, transform .2s ease; }}
  .cert-nav-btn:not(:disabled):hover {{ filter: brightness(1.12); transform: translateY(-1px); }}
</style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">

  <header class="border-b border-slate-800 bg-slate-900/70 backdrop-blur sticky top-0 z-10">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
      <a href="./index.html" class="text-sm font-medium text-slate-400 hover:text-cyan-300 transition-colors flex items-center gap-1">
        <span aria-hidden="true">&larr;</span> Zur&uuml;ck zur Website
      </a>
      <div class="text-center">
        <h1 class="text-lg sm:text-xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">
          Zertifikate &amp; Nachweise
        </h1>
        <p class="text-xs text-slate-500">Mayada Esmail</p>
      </div>
      <span id="cert-counter" class="text-sm font-semibold text-slate-300 bg-slate-800 border border-slate-700 rounded-full px-3 py-1 whitespace-nowrap"></span>
    </div>
  </header>

  <main class="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">

    <aside class="lg:sticky lg:top-24 lg:self-start bg-slate-900 border border-slate-800 rounded-xl p-2 max-h-[70vh] overflow-y-auto" id="cert-list"></aside>

    <section class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
      <div class="flex items-center justify-between px-4 sm:px-5 py-3 border-b border-slate-800 gap-3">
        <button id="cert-prev" class="cert-nav-btn px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg font-semibold text-sm disabled:opacity-30 disabled:cursor-not-allowed">&larr; Vorherige</button>
        <h2 id="cert-title" class="text-sm sm:text-base font-semibold text-center flex-1 truncate"></h2>
        <a id="cert-download" href="#" download class="hidden sm:inline-flex px-3 py-2 bg-gradient-to-r from-blue-600 to-violet-600 rounded-lg font-semibold text-sm items-center gap-1 hover:brightness-110 transition">
          &darr; PDF
        </a>
        <button id="cert-next" class="cert-nav-btn px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg font-semibold text-sm disabled:opacity-30 disabled:cursor-not-allowed">N&auml;chste &rarr;</button>
      </div>
      <iframe id="cert-frame" class="w-full" style="height:75vh;background:#fff;border:0;" title="Zertifikat"></iframe>
    </section>

  </main>

  <footer class="max-w-6xl mx-auto px-4 sm:px-6 pb-10 text-center text-xs text-slate-600">
    {len(certificates)} Zertifikat(e) &middot; mit Pfeiltasten oder den Schaltfl&auml;chen durchbl&auml;ttern
  </footer>

<script>
const certificates = {certificates_json};
let currentIndex = 0;

const frame = document.getElementById('cert-frame');
const title = document.getElementById('cert-title');
const counter = document.getElementById('cert-counter');
const prevBtn = document.getElementById('cert-prev');
const nextBtn = document.getElementById('cert-next');
const downloadLink = document.getElementById('cert-download');
const listEl = document.getElementById('cert-list');

function render() {{
    const cert = certificates[currentIndex];
    frame.src = cert.file;
    title.textContent = cert.name;
    counter.textContent = (currentIndex + 1) + ' / ' + certificates.length;
    downloadLink.href = cert.file;
    downloadLink.setAttribute('download', cert.name + '.pdf');
    prevBtn.disabled = currentIndex === 0;
    nextBtn.disabled = currentIndex === certificates.length - 1;
    Array.from(listEl.children).forEach((item, index) => {{
        item.classList.toggle('active', index === currentIndex);
    }});
    const activeItem = listEl.children[currentIndex];
    if (activeItem) activeItem.scrollIntoView({{ block: 'nearest' }});
}}

certificates.forEach((cert, index) => {{
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'cert-item w-full flex items-center gap-3 text-left px-3 py-2.5 rounded-lg border border-transparent hover:bg-slate-800/70';
    item.innerHTML =
        '<span class="flex-shrink-0 w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-300">' + (index + 1) + '</span>' +
        '<span class="text-sm font-medium text-slate-200 truncate">' + cert.name + '</span>';
    item.addEventListener('click', () => {{ currentIndex = index; render(); }});
    listEl.appendChild(item);
}});

prevBtn.addEventListener('click', () => {{ if (currentIndex > 0) {{ currentIndex--; render(); }} }});
nextBtn.addEventListener('click', () => {{ if (currentIndex < certificates.length - 1) {{ currentIndex++; render(); }} }});
document.addEventListener('keydown', (event) => {{
    if (event.key === 'ArrowLeft') prevBtn.click();
    if (event.key === 'ArrowRight') nextBtn.click();
}});

render();
</script>
</body>
</html>
"""


def add_base_href(html: str, base_url: str) -> str:
    """Fügt ein <base>-Tag ein, damit relative Bild-/Datei-Pfade in der Vorschau
    vom ursprünglichen Server geladen werden, statt in der Vorschau zu brechen."""
    if not base_url or re.search(r"<base[\s>]", html, flags=re.I):
        return html

    if not base_url.endswith("/"):
        base_url = f"{base_url}/"

    base_tag = f'<base href="{base_url}">'

    head_match = re.search(r"<head[^>]*>", html, flags=re.I)
    if head_match:
        insert_at = head_match.end()
        return html[:insert_at] + base_tag + html[insert_at:]

    html_match = re.search(r"<html[^>]*>", html, flags=re.I)
    if html_match:
        insert_at = html_match.end()
        return html[:insert_at] + f"<head>{base_tag}</head>" + html[insert_at:]

    return base_tag + html


def create_preview_html(html: str) -> str:
    """Ersetzt lokale Bildnamen in der Vorschau durch eingebettete Data-URLs."""
    preview_html = html

    for file_name, asset in st.session_state.assets.items():
        data_url = f"data:{asset['mime_type']};base64,{asset['base64']}"
        preview_html = preview_html.replace(file_name, data_url)

    # Bei einer geladenen Original-Website liegen Bilder & Dateien nur auf dem
    # Live-Server – ohne <base>-Tag würden relative Pfade in der Vorschau ins Leere laufen.
    preview_html = add_base_href(preview_html, st.session_state.live_url)

    return add_chatbot_widget(add_project_interactions(preview_html))


def add_project_interactions(html: str) -> str:
        """Ergänzt interaktive Animationen für die Projekt- und Meilensteinsektion."""
        if 'id="portfolio-project-interactions"' in html:
                return html

        interaction_html = """
<style id="portfolio-project-interactions">
@keyframes portfolioProjectEnter { from { opacity:0; transform:translateX(56px); } to { opacity:1; transform:translateX(0); } }
@keyframes portfolioProjectDrift { 0%,100% { translate:0 0; } 50% { translate:12px 0; } }
@keyframes portfolioBadgeEnter { from { opacity:0; transform:translateY(8px) scale(.96); } to { opacity:1; transform:translateY(0) scale(1); } }
@keyframes portfolioAboutTitleEnter { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
@keyframes portfolioHeroEnter { from { opacity:0; transform:translateY(22px); } to { opacity:1; transform:translateY(0); } }
@keyframes portfolioHeroFloat { 0%,100% { translate:0 0; } 50% { translate:0 -7px; } }
@keyframes portfolioCtaShimmer { 0%,100% { box-shadow:0 4px 15px rgba(37,99,235,.2); } 50% { box-shadow:0 8px 24px rgba(124,58,237,.34); } }
@keyframes portfolioNavEnter { from { opacity:0; transform:translateY(-10px); } to { opacity:1; transform:translateY(0); } }
@keyframes portfolioExpertiseEnter { from { opacity:0; transform:translateY(26px) scale(.98); } to { opacity:1; transform:translateY(0) scale(1); } }
@keyframes portfolioExpertiseFloat { 0%,100% { translate:0 0; } 50% { translate:0 -5px; } }
@keyframes portfolioContactEnter { from { opacity:0; transform:translateY(30px); } to { opacity:1; transform:translateY(0); } }
@keyframes portfolioAboutImageFloat { 0%,100% { transform:translateY(0) scale(1); } 50% { transform:translateY(-8px) scale(1.018); } }
.portfolio-project-card { position:relative; isolation:isolate; border:1px solid rgba(30,41,59,.28) !important; transform-style:preserve-3d; transition:transform .4s ease, border-color .4s ease, box-shadow .4s ease !important; will-change:transform; }
.portfolio-project-card::before { content:''; position:absolute; inset:-1px; z-index:-1; border-radius:inherit; opacity:0; padding:1px; background:linear-gradient(125deg,#2563eb,#7c3aed,#22d3ee); transition:opacity .4s ease; -webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0); -webkit-mask-composite:xor; mask-composite:exclude; pointer-events:none; }
.portfolio-project-card:hover { border-color:transparent !important; box-shadow:0 10px 30px rgba(124,58,237,.15),0 18px 46px rgba(37,99,235,.14) !important; }
.portfolio-project-card:hover::before { opacity:1; }
.portfolio-project-card.portfolio-project-reveal { opacity:0; }
.portfolio-project-card.portfolio-project-reveal.is-visible { animation:portfolioProjectEnter .7s cubic-bezier(.2,.75,.25,1) forwards,portfolioProjectDrift 4.8s ease-in-out .8s infinite; }
.portfolio-project-card:nth-child(2) { animation-delay:0ms,1.55s !important; }
.portfolio-project-card:nth-child(3) { animation-delay:0ms,2.3s !important; }
.portfolio-tech-badge { display:inline-flex; align-items:center; transition:transform .22s ease,background-color .22s ease,color .22s ease,box-shadow .22s ease !important; animation:portfolioBadgeEnter .45s ease both; }
.portfolio-tech-badge:hover { transform:scale(1.05); background-color:#2563eb !important; color:#fff !important; box-shadow:0 5px 14px rgba(37,99,235,.25); }
.portfolio-about-title { position:relative; display:inline-block; animation:portfolioAboutTitleEnter .8s cubic-bezier(.2,.75,.25,1) both; }
.portfolio-about-title::after { content:''; display:block; width:56%; height:3px; margin-top:9px; background:linear-gradient(90deg,#0f766e,#38bdf8); border-radius:2px; transform-origin:left; animation:portfolioProjectEnter .7s .35s cubic-bezier(.2,.75,.25,1) both; }
.portfolio-about-image { animation:portfolioAboutImageFloat 5.5s ease-in-out infinite; transition:filter .35s ease,box-shadow .35s ease !important; will-change:transform; }
.portfolio-about-image:hover { filter:saturate(1.08) contrast(1.03); box-shadow:0 16px 34px rgba(14,116,144,.24); }
.portfolio-hero-title { animation:portfolioHeroEnter .8s cubic-bezier(.2,.75,.25,1) both,portfolioHeroFloat 5s ease-in-out .9s infinite; }
.portfolio-hero-copy { animation:portfolioHeroEnter .7s .18s cubic-bezier(.2,.75,.25,1) both; }
.portfolio-hero-actions { animation:portfolioHeroEnter .7s .36s cubic-bezier(.2,.75,.25,1) both; }
.portfolio-hero-actions > button, .portfolio-hero-actions > a { transition:transform .25s ease,filter .25s ease,box-shadow .25s ease !important; will-change:transform; }
.portfolio-hero-actions > button:first-child { animation:portfolioCtaShimmer 3s ease-in-out .9s infinite; }
.portfolio-hero-actions > button:hover, .portfolio-hero-actions > a:hover { transform:translateY(-4px) scale(1.02); filter:brightness(1.08); }
.portfolio-nav-link { position:relative; display:inline-block; transition:color .25s ease,transform .25s ease !important; animation:portfolioNavEnter .55s ease both; }
.portfolio-nav-link::after { content:''; position:absolute; left:0; right:0; bottom:-6px; height:2px; background:#fbbf24; border-radius:2px; transform:scaleX(0); transform-origin:center; transition:transform .25s ease; }
.portfolio-nav-link:hover { color:#fbbf24 !important; transform:translateY(-2px); }
.portfolio-nav-link:hover::after { transform:scaleX(1); }
.portfolio-sticky-nav { position:sticky !important; top:0; z-index:900; backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); box-shadow:0 8px 24px rgba(15,23,42,.12); }
section[id], [data-about], [data-projects], [data-milestones], [data-contact] { scroll-margin-top:96px; }
.portfolio-expertise-card { position:relative; overflow:hidden; transition:transform .35s ease,border-color .35s ease,box-shadow .35s ease !important; animation:portfolioExpertiseEnter .7s cubic-bezier(.2,.75,.25,1) both,portfolioExpertiseFloat 5.5s ease-in-out .8s infinite; }
.portfolio-expertise-card::before { content:''; position:absolute; inset:0; opacity:0; background:linear-gradient(130deg,rgba(56,189,248,.13),transparent 48%,rgba(124,58,237,.13)); transition:opacity .35s ease; pointer-events:none; }
.portfolio-expertise-card:hover { transform:translateY(-7px) !important; border-color:#38bdf8 !important; box-shadow:0 14px 34px rgba(37,99,235,.17),0 8px 22px rgba(124,58,237,.12) !important; }
.portfolio-expertise-card:hover::before { opacity:1; }
.portfolio-expertise-card .portfolio-expertise-tag { display:inline-block; transition:transform .22s ease,color .22s ease,text-shadow .22s ease !important; }
.portfolio-expertise-card .portfolio-expertise-tag:hover { transform:translateY(-2px) scale(1.06); color:#67e8f9 !important; text-shadow:0 0 16px rgba(103,232,249,.48); }
.portfolio-contact-section { position:relative; }
.portfolio-contact-section::before { content:''; position:absolute; top:0; left:50%; width:74px; height:3px; background:linear-gradient(90deg,#0f766e,#38bdf8); border-radius:2px; transform:translateX(-50%); }
.portfolio-contact-title { animation:portfolioContactEnter .75s cubic-bezier(.2,.75,.25,1) both; }
.portfolio-contact-form { animation:portfolioContactEnter .75s .18s cubic-bezier(.2,.75,.25,1) both; }
.portfolio-contact-form input, .portfolio-contact-form textarea { transition:border-color .25s ease,box-shadow .25s ease,transform .25s ease !important; }
.portfolio-contact-form input:focus, .portfolio-contact-form textarea:focus { border-color:#38bdf8 !important; box-shadow:0 0 0 4px rgba(56,189,248,.15); transform:translateY(-1px); outline:none; }
.portfolio-contact-form button[type="submit"] { transition:transform .25s ease,filter .25s ease,box-shadow .25s ease !important; box-shadow:0 7px 18px rgba(15,118,110,.22); }
.portfolio-contact-form button[type="submit"]:hover { transform:translateY(-3px); filter:brightness(1.08); box-shadow:0 12px 24px rgba(15,118,110,.3); }
@media (prefers-reduced-motion:reduce) { .portfolio-project-card, .portfolio-tech-badge, .portfolio-about-title, .portfolio-about-image, .portfolio-hero-title, .portfolio-hero-copy, .portfolio-hero-actions, .portfolio-hero-actions > button:first-child, .portfolio-nav-link, .portfolio-expertise-card, .portfolio-contact-title, .portfolio-contact-form { animation:none !important; transition:none !important; } }
</style>
<script>
(() => {
    const section = document.querySelector('#projects, #projekte, [data-projects], [data-milestones]');
    const aboutSection = document.querySelector('#about, #ueber-mich, #über-mich, [data-about]');
    if (aboutSection) {
        const aboutTitle = aboutSection.querySelector('h1, h2, h3');
        if (aboutTitle) aboutTitle.classList.add('portfolio-about-title');
        aboutSection.querySelectorAll('img').forEach((image) => image.classList.add('portfolio-about-image'));
    }
    const hero = document.querySelector('header, #hero, [data-hero], main > section:first-of-type');
    if (hero) {
        const heroTitle = hero.querySelector('h1, h2');
        if (heroTitle) heroTitle.classList.add('portfolio-hero-title');
        const heroText = hero.querySelector('p');
        if (heroText) heroText.classList.add('portfolio-hero-copy');
        const heroActions = Array.from(hero.querySelectorAll('div')).find((element) => Array.from(element.children).some((child) => child.matches('button, a')));
        if (heroActions) heroActions.classList.add('portfolio-hero-actions');
    }
    const navigation = document.querySelector('nav');
    if (navigation) {
        navigation.classList.add('portfolio-sticky-nav');
        navigation.querySelectorAll('a').forEach((link, index) => {
            link.classList.add('portfolio-nav-link');
            link.style.animationDelay = `${index * 90}ms`;
        });
    }
    const expertiseTitle = Array.from(document.querySelectorAll('h1, h2, h3')).find((heading) => /core expertise|tech stack|kompetenzen|fähigkeiten/i.test(heading.textContent || ''));
    if (expertiseTitle) {
        const expertiseSection = expertiseTitle.closest('section') || expertiseTitle.parentElement?.parentElement;
        const expertiseGrid = expertiseSection && Array.from(expertiseSection.querySelectorAll('div')).find((element) => element.classList.contains('grid'));
        if (expertiseGrid) {
            Array.from(expertiseGrid.children).forEach((card, cardIndex) => {
                card.classList.add('portfolio-expertise-card');
                card.style.animationDelay = `${cardIndex * 130}ms,${.8 + cardIndex * .45}s`;
                card.querySelectorAll('span, a, small, li').forEach((tag) => tag.classList.add('portfolio-expertise-tag'));
            });
        }
    }
    const contactSection = document.querySelector('#contact, #kontakt, [data-contact]');
    if (contactSection) {
        contactSection.classList.add('portfolio-contact-section');
        const contactTitle = contactSection.querySelector('h1, h2, h3');
        if (contactTitle) contactTitle.classList.add('portfolio-contact-title');
        const contactForm = contactSection.querySelector('form');
        if (contactForm) contactForm.classList.add('portfolio-contact-form');
    }
    if (!section) return;
    const grid = Array.from(section.querySelectorAll('div')).find((element) => element.classList.contains('grid'));
    const cards = grid ? Array.from(grid.children).filter((element) => element.nodeType === 1) : [];
    cards.forEach((card, index) => {
        card.classList.add('portfolio-project-card', 'portfolio-project-reveal');
        card.style.animationDelay = `${index * 110}ms`;
        card.addEventListener('mousemove', (event) => {
            const bounds = card.getBoundingClientRect();
            const rotateY = ((event.clientX - bounds.left) / bounds.width - .5) * 7;
            const rotateX = ((event.clientY - bounds.top) / bounds.height - .5) * -7;
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-5px)`;
        });
        card.addEventListener('mouseleave', () => { card.style.transform = ''; });
        Array.from(card.querySelectorAll('span, a, small')).forEach((badge, badgeIndex) => {
            if (badge.textContent.trim() && badge.textContent.length < 45) {
                badge.classList.add('portfolio-tech-badge');
                badge.style.animationDelay = `${220 + index * 110 + badgeIndex * 75}ms`;
            }
        });
    });
    if (!cards.length) return;
    const revealVisibleCards = () => cards.forEach((card) => {
        const bounds = card.getBoundingClientRect();
        if (bounds.top < window.innerHeight - 40 && bounds.bottom > 40) {
            card.classList.add('is-visible');
        }
    });
    revealVisibleCards();
    window.addEventListener('scroll', revealVisibleCards, { passive:true });
    window.addEventListener('resize', revealVisibleCards);
})();
</script>
"""

        return re.sub(
            r"</body\s*>",
            lambda _match: interaction_html + "</body>",
            html,
            count=1,
            flags=re.I,
        )


def add_chatbot_widget(html: str) -> str:
        """Fügt den serverseitig angebundenen Portfolio-Chat vor dem Body-Ende ein."""
        if 'id="portfolio-chatbot"' in html:
                return html

        chatbot_html = """
<style>
@keyframes portfolioChatEnter { from { opacity:0; transform:translateY(18px) scale(.98); } to { opacity:1; transform:translateY(0) scale(1); } }
@keyframes portfolioChatPulse { 0%,100% { box-shadow:0 0 0 0 rgba(45,212,191,.38); } 50% { box-shadow:0 0 0 5px rgba(45,212,191,0); } }
@keyframes portfolioChatFloat { 0%,100% { translate:0 0; } 50% { translate:0 -6px; } }
#portfolio-chatbot { animation:portfolioChatEnter .55s ease-out both,portfolioChatFloat 5s ease-in-out .65s infinite; }
#portfolio-chatbot.chat-collapsed { width:min(280px,calc(100vw - 28px)) !important; }
#portfolio-chatbot.chat-collapsed #portfolio-chat-toggle { width:100%;min-height:64px;padding:10px 12px;border-radius:8px;background:#0b172a; }
#portfolio-chatbot.chat-collapsed .portfolio-chat-glow, #portfolio-chatbot.chat-collapsed .portfolio-chat-control { display:none !important; }
#portfolio-chat-tooltip { display:none; }
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
    <section id="portfolio-chat-panel" style="margin-top:7px;background:#fff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 20px 48px rgba(15,23,42,.24);overflow:hidden;">
        <div id="portfolio-chat-messages" aria-live="polite" style="height:230px;overflow-y:auto;padding:15px;background:#fff;color:#1e293b;font-size:14px;line-height:1.55;"><p style="max-width:90%;margin:0;padding:11px 12px;background:#eefbf8;border-left:3px solid #0f766e;border-radius:0 7px 7px 0;">Willkommen. Wobei kann ich Sie zu Mayadas Profil unterstützen?</p></div>
        <div id="portfolio-chat-suggestions" style="display:flex;flex-wrap:wrap;gap:6px;padding:0 13px 13px;background:#fff;"><button type="button" data-question="Welche Kompetenzen bringt Mayada mit?" style="padding:6px 8px;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;font-weight:650;">Kompetenzen</button><button type="button" data-question="Welche Projekterfahrung hat Mayada?" style="padding:6px 8px;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;font-weight:650;">Projekterfahrung</button><button type="button" data-question="Ist Mayada für mein Projekt geeignet?" style="padding:6px 8px;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;font-weight:650;">Projektanfrage</button></div>
        <form id="portfolio-chat-form" style="display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0;background:#fff;">
            <input id="portfolio-chat-input" type="text" aria-label="Frage an den Portfolio-Assistenten" placeholder="Ihre Frage eingeben..." required style="min-width:0;flex:1;padding:10px 11px;color:#0f172a;background:#fff;border:1px solid #94a3b8;border-radius:6px;font:inherit;font-size:14px;outline-offset:2px;">
            <button id="portfolio-chat-mic" type="button" aria-label="Frage per Sprache eingeben" title="Frage sprechen" style="width:40px;padding:0;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:6px;cursor:pointer;font-size:16px;">&#127908;</button>
            <button id="portfolio-chat-submit" type="submit" aria-label="Frage senden" style="padding:10px 14px;background:#0f766e;color:#fff;border:0;border-radius:6px;cursor:pointer;font:inherit;font-size:13px;font-weight:800;box-shadow:0 4px 10px rgba(15,118,110,.22);">Senden</button>
            <button id="portfolio-chat-voice" type="button" aria-pressed="true" aria-label="Antworten vorlesen: an" title="Antworten vorlesen" style="width:40px;padding:0;background:#f8fafc;color:#0f766e;border:1px solid #99f6e4;border-radius:6px;cursor:pointer;font-size:16px;">&#128266;</button>
        </form>
    </section>
</aside>
<script>
(() => {
    const toggle = document.getElementById('portfolio-chat-toggle');
    const panel = document.getElementById('portfolio-chat-panel');
    const form = document.getElementById('portfolio-chat-form');
    const input = document.getElementById('portfolio-chat-input');
    const mic = document.getElementById('portfolio-chat-mic');
    const submit = document.getElementById('portfolio-chat-submit');
    const voice = document.getElementById('portfolio-chat-voice');
    const messages = document.getElementById('portfolio-chat-messages');
    const history = [];
    let voiceEnabled = true;
    const cleanAssistantText = (text) => text
        .replace(/\*\*/g, '')
        .replace(/__/g, '')
        .replace(/`/g, '')
        .replace(/\*/g, '')
        .trim();
    const splitIntoSpeechChunks = (text) => text
        .split(/\n+/)
        .map((line) => line
            .replace(/^[ \t]*[-•][ \t]*/, '')
            .replace(/^[ \t]*\d+[.)][ \t]*/, '')
            .trim())
        .filter(Boolean)
        .flatMap((line) => line.match(/[^.!?]+[.!?]*/g) || [line])
        .map((chunk) => chunk.replace(/\s{2,}/g, ' ').trim())
        .filter(Boolean);
    let preferredVoice = null;
    const pickPreferredVoice = () => {
        if (!('speechSynthesis' in window)) return null;
        const voices = window.speechSynthesis.getVoices();
        if (!voices.length) return null;
        const germanVoices = voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith('de'));
        const pool = germanVoices.length ? germanVoices : voices;
        const preferredNameHints = ['online (natural)', 'natural', 'google', 'online', 'katja', 'conrad', 'female'];
        for (const hint of preferredNameHints) {
            const match = pool.find((v) => v.name.toLowerCase().includes(hint));
            if (match) return match;
        }
        return pool[0] || null;
    };
    if ('speechSynthesis' in window) {
        preferredVoice = pickPreferredVoice();
        window.speechSynthesis.addEventListener('voiceschanged', () => {
            preferredVoice = pickPreferredVoice();
        });
    }
    const speak = (text) => {
        if (!voiceEnabled || !('speechSynthesis' in window)) return;
        window.speechSynthesis.cancel();
        const chunks = splitIntoSpeechChunks(text);
        chunks.forEach((chunk) => {
            const utterance = new SpeechSynthesisUtterance(chunk);
            utterance.lang = preferredVoice ? preferredVoice.lang : 'de-DE';
            if (preferredVoice) utterance.voice = preferredVoice;
            utterance.rate = 1;
            utterance.pitch = 1;
            window.speechSynthesis.speak(utterance);
        });
    };
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
            const answer = cleanAssistantText(data.answer);
            addMessage(answer, 'Assistent');
            history.push({role: 'assistant', content: answer});
            speak(answer);
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
    voice.addEventListener('click', () => {
        voiceEnabled = !voiceEnabled;
        voice.setAttribute('aria-pressed', String(voiceEnabled));
        voice.setAttribute('aria-label', 'Antworten vorlesen: ' + (voiceEnabled ? 'an' : 'aus'));
        voice.style.background = voiceEnabled ? '#f8fafc' : '#e2e8f0';
        if (!voiceEnabled && 'speechSynthesis' in window) window.speechSynthesis.cancel();
    });
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    const setMicState = (state) => {
        if (state === 'listening') {
            mic.innerHTML = '&#9679;';
            mic.style.background = '#fee2e2';
            mic.style.color = '#b91c1c';
            mic.title = 'Aufnahme läuft – zum Beenden klicken';
        } else if (state === 'processing') {
            mic.innerHTML = '...';
            mic.style.background = '#f8fafc';
            mic.style.color = '#0f766e';
            mic.title = 'Sprache wird verarbeitet...';
        } else {
            mic.innerHTML = '&#127908;';
            mic.style.background = '#f8fafc';
            mic.style.color = '#0f766e';
            mic.title = 'Frage sprechen';
        }
    };
    const startNativeRecognition = () => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.lang = 'de-DE';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        mic.disabled = true;
        setMicState('listening');
        recognition.onresult = (event) => {
            const transcript = (event.results[0][0].transcript || '').trim();
            if (transcript) {
                input.value = transcript;
                form.requestSubmit();
            }
        };
        recognition.onerror = (event) => {
            const message = event.error === 'not-allowed' || event.error === 'permission-denied'
                ? 'Der Zugriff auf das Mikrofon wurde verweigert. Bitte erlauben Sie den Zugriff in den Browser-Einstellungen.'
                : event.error === 'no-speech'
                    ? 'Es wurde keine Sprache erkannt. Bitte versuchen Sie es erneut.'
                    : 'Die Spracheingabe konnte nicht gestartet werden. Bitte versuchen Sie es erneut.';
            addMessage(message, 'Hinweis');
        };
        recognition.onend = () => {
            mic.disabled = false;
            setMicState('idle');
        };
        recognition.start();
    };
    const stopFallbackRecording = () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
    };
    const startFallbackRecording = async () => {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined') {
            addMessage('Die Spracheingabe wird von diesem Browser nicht unterstützt. Bitte tippen Sie Ihre Frage ein.', 'Hinweis');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            const mimeType = (typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported('audio/webm'))
                ? 'audio/webm'
                : '';
            mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
            isRecording = true;
            setMicState('listening');
            mediaRecorder.addEventListener('dataavailable', (event) => {
                if (event.data && event.data.size > 0) audioChunks.push(event.data);
            });
            mediaRecorder.addEventListener('stop', async () => {
                isRecording = false;
                stream.getTracks().forEach((track) => track.stop());
                setMicState('processing');
                mic.disabled = true;
                try {
                    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                    if (blob.size < 1000) {
                        throw new Error('Die Aufnahme war zu kurz. Bitte versuchen Sie es erneut.');
                    }
                    const response = await fetch('/api/transcribe', {
                        method: 'POST',
                        headers: { 'Content-Type': blob.type || 'audio/webm' },
                        body: blob,
                    });
                    const contentType = response.headers.get('content-type') || '';
                    const data = contentType.includes('application/json') ? await response.json() : {};
                    if (!response.ok) {
                        const message = response.status === 404 || response.status === 405
                            ? 'Die Spracherkennung wird nach der Veröffentlichung auf Vercel aktiv.'
                            : (data.error || 'Die Sprachaufnahme konnte nicht verarbeitet werden.');
                        throw new Error(message);
                    }
                    const transcript = (data.text || '').trim();
                    if (!transcript) {
                        throw new Error('Es wurde keine Sprache erkannt. Bitte versuchen Sie es erneut.');
                    }
                    input.value = transcript;
                    form.requestSubmit();
                } catch (error) {
                    addMessage(error.message, 'Hinweis');
                } finally {
                    mic.disabled = false;
                    setMicState('idle');
                }
            });
            mediaRecorder.start();
            setTimeout(() => { if (isRecording) stopFallbackRecording(); }, 15000);
        } catch (error) {
            setMicState('idle');
            addMessage('Der Zugriff auf das Mikrofon wurde verweigert oder ist nicht möglich.', 'Hinweis');
        }
    };
    mic.addEventListener('click', () => {
        if (isRecording) {
            stopFallbackRecording();
            return;
        }
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            startNativeRecognition();
        } else {
            startFallbackRecording();
        }
    });
})();
</script>
"""

        return re.sub(
            r"</body\s*>",
            lambda _match: chatbot_html + "</body>",
            html,
            count=1,
            flags=re.I,
        )


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

    <!-- Button 3: Öffnet die Zertifikate-Übersicht direkt über einen absoluten Link -->
    <a href="./zertifikate.html"
         target="_blank"
         style="padding: 12px 24px; background: #1e293b; color: #f1f5f9; font-weight: 600; border: 1px solid #334155; border-radius: 8px; text-decoration: none; display: inline-block;">
        Zertifikate ansehen
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

    <!-- Button 3: Öffnet die Zertifikate-Übersicht direkt über einen absoluten Link -->
    <a href="./zertifikate.html"
         target="_blank"
         style="padding: 12px 24px; background: #1e293b; color: #f1f5f9; font-weight: 600; border: 1px solid #334155; border-radius: 8px; text-decoration: none; display: inline-block;">
        Zertifikate ansehen
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


def upload_file_to_vercel(content: bytes) -> str:
    """Lädt Datei-Inhalte einzeln zu Vercel hoch (umgeht das 10-MB-Limit der Deployment-API)."""
    digest = hashlib.sha1(content).hexdigest()

    try:
        response = requests.post(
            "https://api.vercel.com/v2/files",
            headers={
                "Authorization": f"Bearer {VERCEL_TOKEN}",
                "Content-Length": str(len(content)),
                "x-vercel-digest": digest,
            },
            data=content,
            timeout=90,
        )
    except requests.RequestException as error:
        raise ValueError(f"Vercel-Datei-Upload konnte nicht erreicht werden: {error}") from error

    if response.status_code not in (200, 201):
        raise ValueError(f"Vercel-Datei-Upload HTTP {response.status_code}: {response.text}")

    return digest


def publish_website() -> None:
    """Veröffentlicht den aktuellen HTML-Entwurf auf Vercel."""
    html = add_chatbot_widget(
        add_project_interactions(require_complete_html(st.session_state.generated_html))
    )
    project_name = safe_project_name(st.session_state.project_name)

    raw_files: list[tuple[str, bytes]] = [
        ("index.html", html.encode("utf-8")),
        (
            "api/chat.py",
            Path(__file__).with_name("api").joinpath("chat.py").read_bytes(),
        ),
        (
            "api/transcribe.py",
            Path(__file__).with_name("api").joinpath("transcribe.py").read_bytes(),
        ),
        (
            "api/requirements.txt",
            Path(__file__)
            .with_name("api")
            .joinpath("requirements.txt")
            .read_bytes(),
        ),
    ]

    if not RESUME_FILE_PATH.is_file():
        raise ValueError(
            f"Die Lebenslauf-Datei '{RESUME_FILE_NAME}' wurde nicht gefunden."
        )

    raw_files.append((RESUME_FILE_NAME, RESUME_FILE_PATH.read_bytes()))

    certificate_paths = get_certificate_files()
    if not certificate_paths:
        raise ValueError(
            f"Im Ordner '{CERTIFICATE_DIR}' wurden keine Zertifikats-PDFs gefunden."
        )

    certificate_entries = []
    for index, certificate_path in enumerate(certificate_paths, start=1):
        deploy_file_name = f"zertifikate/{slugify_certificate_filename(certificate_path.stem, index)}"
        certificate_entries.append(
            {
                "file": deploy_file_name,
                "name": prettify_certificate_name(certificate_path.stem),
            }
        )
        raw_files.append((deploy_file_name, certificate_path.read_bytes()))

    raw_files.append(
        (
            CERTIFICATE_VIEWER_FILE_NAME,
            build_certificate_viewer_html(certificate_entries).encode("utf-8"),
        )
    )

    for file_name, asset in st.session_state.assets.items():
        raw_files.append((file_name, base64.b64decode(asset["base64"])))

    # Jede Datei wird einzeln zu Vercel hochgeladen und im Deployment nur per
    # SHA1-Hash referenziert, da die Deployment-API selbst auf 10 MB begrenzt ist.
    files = [
        {"file": file_name, "sha": upload_file_to_vercel(content), "size": len(content)}
        for file_name, content in raw_files
    ]

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