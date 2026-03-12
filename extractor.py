"""
Badge-Extraktor  –  Kernlogik
OCR: Tesseract (lokal, kostenlos)
Textanalyse + E-Mail-Recherche: Perplexity Sonar API
"""

import json
import re
import time
from pathlib import Path

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from openai import OpenAI


# ──────────────────────────────────────────────────────────────
# Perplexity-Client (OpenAI-kompatibel)
# ──────────────────────────────────────────────────────────────

def _perplexity_client(api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
    )


# ──────────────────────────────────────────────────────────────
# 1. Bildvorverarbeitung für Tesseract
# ──────────────────────────────────────────────────────────────

def _preprocess(image_path: str | Path) -> Image.Image:
    """Verbessert Schärfe und Kontrast für bessere OCR-Ergebnisse."""
    img = Image.open(image_path).convert("RGB")

    # Auf sinnvolle Größe bringen (Tesseract mag ~300dpi)
    w, h = img.size
    scale = max(1.0, 1800 / max(w, h))
    if scale > 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Kontrast und Schärfe erhöhen
    img = ImageEnhance.Contrast(img).enhance(1.6)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    return img


# ──────────────────────────────────────────────────────────────
# 2. OCR mit Tesseract
# ──────────────────────────────────────────────────────────────

def ocr_image(image_path: str | Path) -> str:
    """Liest den Text eines Badge-Fotos mit Tesseract aus.
    Probiert Deutsch+Englisch; gibt den rohen OCR-Text zurück."""
    img = _preprocess(image_path)
    # LSTM-Engine, Deutsch+Englisch
    config = r"--oem 1 --psm 6"
    try:
        text = pytesseract.image_to_string(img, lang="deu+eng", config=config)
    except Exception:
        # Fallback: nur Englisch
        text = pytesseract.image_to_string(img, lang="eng", config=config)
    return text.strip()


# ──────────────────────────────────────────────────────────────
# 3. Strukturextraktion via Perplexity Sonar
# ──────────────────────────────────────────────────────────────

EXTRACT_PROMPT = """Du bekommst den per OCR ausgelesenen Rohtext eines Konferenz-Namensbadges.
Extrahiere daraus die folgenden Felder, soweit erkennbar:
- nachname
- vorname
- institution  (Firmen- oder Institutsname)
- ort          (Stadt / Standort)

Antworte NUR mit einem JSON-Objekt, ohne Markdown-Codeblock, ohne Erklärung:
{"nachname": "...", "vorname": "...", "institution": "...", "ort": "..."}

Felder, die nicht erkennbar sind, gibst du als leeren String "" zurück.
Korrigiere offensichtliche OCR-Fehler (z. B. "0" statt "O", "l" statt "I").
"""


def extract_badge_fields(ocr_text: str, api_key: str) -> dict:
    """Schickt den OCR-Text an Perplexity Sonar und gibt strukturierte Felder zurück."""
    client = _perplexity_client(api_key)

    resp = client.chat.completions.create(
        model="sonar",
        messages=[
            {"role": "system", "content": "Du extrahierst strukturierte Daten aus OCR-Text. Antworte ausschließlich mit dem angeforderten JSON."},
            {"role": "user", "content": f"{EXTRACT_PROMPT}\n\nOCR-Text:\n{ocr_text}"},
        ],
        max_tokens=200,
        temperature=0,
    )

    raw = resp.choices[0].message.content.strip()
    # JSON bereinigen
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    # Nur das erste { ... } nehmen
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    data = json.loads(m.group(0)) if m else {}

    return {
        "Nachname":    data.get("nachname", ""),
        "Vorname":     data.get("vorname", ""),
        "Institution": data.get("institution", ""),
        "Ort":         data.get("ort", ""),
        "E-Mail":      "",
        "Quelle":      "",
    }


def extract_badge_data(image_path: str | Path, api_key: str) -> dict:
    """Vollständige Pipeline: Bild → OCR → Feldextraktion."""
    ocr_text = ocr_image(image_path)
    if not ocr_text:
        return {"Nachname": "", "Vorname": "", "Institution": "", "Ort": "", "E-Mail": "", "Quelle": "OCR leer"}
    return extract_badge_fields(ocr_text, api_key)


# ──────────────────────────────────────────────────────────────
# 4. E-Mail-Recherche via Perplexity Sonar (web-grounded)
# ──────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

EMAIL_SEARCH_PROMPT = """\
Ich suche die offizielle, öffentlich zugängliche E-Mail-Adresse von:
Name: {vorname} {nachname}
Institution: {institution}
Ort: {ort}

Bitte suche im Web nach der konkreten E-Mail-Adresse dieser Person.
Antworte NUR mit einem JSON-Objekt:
{{"email": "gefundene@adresse.de", "quelle": "https://url-der-quelle.de"}}
Wenn keine E-Mail gefunden wurde: {{"email": "", "quelle": ""}}
Keine weiteren Erklärungen.
"""


def find_email(
    vorname: str,
    nachname: str,
    institution: str,
    ort: str,
    api_key: str,
) -> tuple[str, str]:
    """
    Nutzt Perplexity Sonar (web-grounded) zur E-Mail-Recherche.
    Gibt (email, quell_url) zurück.
    """
    if not nachname and not vorname:
        return "", ""

    client = _perplexity_client(api_key)
    prompt = EMAIL_SEARCH_PROMPT.format(
        vorname=vorname,
        nachname=nachname,
        institution=institution or "unbekannt",
        ort=ort or "unbekannt",
    )

    try:
        resp = client.chat.completions.create(
            model="sonar",          # hat eingebaute Web-Suche
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du suchst öffentlich zugängliche E-Mail-Adressen von Personen im Web. "
                        "Antworte ausschließlich mit dem angeforderten JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            email = data.get("email", "").strip()
            source = data.get("quelle", "").strip()
            # Plausibilitätscheck
            if email and EMAIL_RE.fullmatch(email):
                return email, source
    except Exception:
        pass

    return "", ""
