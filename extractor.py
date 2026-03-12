"""
Badge-Extraktor  –  Kernlogik
OCR: Tesseract (lokal, kostenlos)
Textanalyse + Recherche: Perplexity Sonar API
"""

import json
import re
from pathlib import Path

import pytesseract
from PIL import Image, ImageEnhance
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
    config = r"--oem 1 --psm 6"
    try:
        text = pytesseract.image_to_string(img, lang="deu+eng", config=config)
    except Exception:
        text = pytesseract.image_to_string(img, lang="eng", config=config)
    return text.strip()


# ──────────────────────────────────────────────────────────────
# 3. Strukturextraktion via Perplexity Sonar (Basisdaten vom Badge)
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
            {
                "role": "system",
                "content": (
                    "Du extrahierst strukturierte Daten aus OCR-Text. "
                    "Antworte ausschließlich mit dem angeforderten JSON."
                ),
            },
            {"role": "user", "content": f"{EXTRACT_PROMPT}\n\nOCR-Text:\n{ocr_text}"},
        ],
        max_tokens=200,
        temperature=0,
    )

    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    data = json.loads(m.group(0)) if m else {}

    # Normalisierung: erster Buchstabe groß, Rest klein
    def _norm_name(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        return s[0].upper() + s[1:].lower()

    nachname = _norm_name(data.get("nachname", ""))
    vorname = _norm_name(data.get("vorname", ""))

    return {
        "Nachname": nachname,
        "Vorname": vorname,
        "Institution": data.get("institution", "").strip(),
        "Ort": data.get("ort", "").strip(),
        # E-Mail & Quelle/Website werden in Schritt 4 ergänzt
        "E-Mail": "",
        "Quelle": "",
        "Position/Funktion": "",
    }


def extract_badge_data(image_path: str | Path, api_key: str) -> dict:
    """Vollständige Pipeline: Bild → OCR → Feldextraktion."""
    ocr_text = ocr_image(image_path)
    if not ocr_text:
        return {
            "Nachname": "",
            "Vorname": "",
            "Institution": "",
            "Ort": "",
            "E-Mail": "",
            "Quelle": "OCR leer",
            "Position/Funktion": "",
        }
    return extract_badge_fields(ocr_text, api_key)


# ──────────────────────────────────────────────────────────────
# 4. Detaillierte Web-Recherche via Perplexity Sonar
#    (Institution, Position, Ort, E-Mail, Website)
# ──────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

DETAILED_SEARCH_PROMPT = """Du bist ein hochspezialisierter Recherche-Assistent für
Konferenz-Badges im Bereich Humangenetik und verwandten Fächern
(Medizinische Genetik, Molekulargenetik, Onkologie, Pathologie).

Aufgabe:
Für die folgende Person sollst du eine berufliche Kontaktzeile
recherchieren und strukturieren:

Vorname: {vorname}
Nachname: {nachname}
Ort (Badge): {ort}
Institution (Badge, falls vorhanden): {institution}

WICHTIG:
- Du darfst Informationen NICHT erfinden.
- Bevor du eine E-Mailadresse akzeptierst, prüfe, ob sie auf einer
  offiziellen Seite einer Uni, eines Klinikums oder Instituts steht.
- Wenn du dir nicht sicher bist, setze das Feld auf "nicht gefunden".

Vorgehen (immer in dieser Reihenfolge):

1. Fokussierte Websuche
   - Suche nach Kombinationen wie:
     - "{vorname} {nachname} {ort} Humangenetik"
     - "{vorname} {nachname} Humangenetik"
     - "{vorname} {nachname} Medizinische Genetik"
   - Ignoriere Treffer, die offensichtlich nichts mit Medizin /
     Biologie / Klinik / Labor zu tun haben.

2. Offizielle Institution identifizieren
   - Bevorzuge Domains mit TLDs wie:
       .ac.at, .uni-*.*, .meduni-*, .uni-*, .de, .at
     und Klinik-/Uni-Klinik-Seiten (z.B. "uniklinikum", "klinikum",
     "uk-", "meduni", "i-med", "uk-essen", "uk-erlangen").
   - Vermeide Social-Media-Profile (LinkedIn, X, ResearchGate)
     als Primärquelle. Nutze sie höchstens, um die Institution zu
     identifizieren und gehe dann auf die offizielle Seite.

3. Team- oder Kontaktseite öffnen
   - Öffne explizit eine Team-/Mitarbeiter-/Kontaktseite der gefundenen
     Institution (z.B. Seite mit "Team", "Mitarbeiter", "Klinik",
     "Institut", "Department", "Sektion").
   - Suche innerhalb dieser Seite per String-Suche nach:
       - dem vollständigen Namen "{vorname} {nachname}"
       - falls nötig auch nur nach dem Nachnamen "{nachname}".

4. Daten aus dem Eintrag extrahieren
   Wenn die Person in einer Team-/Kontakt-/Mitarbeiterliste gefunden wird,
   extrahiere:
   - exakte Bezeichnung der Institution
     (inkl. Universität/Klinikum und ggf. Klinik/Institut/Abteilung/Sektion)
   - Ort der Institution (z.B. Innsbruck, Essen, Erlangen)
   - Positions-/Funktionsbezeichnung (z.B. "Fachärztin für Humangenetik")
   - dienstliche E-Mailadresse
   - direkte URL des Eintrags (Personenprofil oder Teamseite)

5. Falls keine passende Team-/Kontaktseite mit Eintrag auffindbar ist:
   - Versuche, aus offiziellen Uni-/Klinik-Seiten (z.B. PDF, Organigramm,
     Projektseite) dennoch eine seriöse E-Mailadresse zu finden.
   - Akzeptiere E-Mailadressen nur, wenn sie klar im Kontext der
     Institution stehen.
   - Wenn auch das nicht möglich ist:
       - setze die E-Mailadresse auf "nicht gefunden"
       - gib die plausibelste Institution + Ort an, die du finden konntest
         (oder "nicht gefunden", falls auch das unklar ist).

BEISPIEL-AUSGABEN:

Beispiel 1 (vollständig gefunden):
{
  "nachname": "Weiss",
  "vorname": "Luisa",
  "institution": "Universitätsklinikum Erlangen, Humangenetik",
  "position": "Fachärztin für Humangenetik, Dr. med.",
  "ort": "Erlangen",
  "email": "luisa.weiss@uk-erlangen.de",
  "website": "https://www.humangenetik.uk-erlangen.de/ueber-uns/team/wissenschaftliche-mitarbeiter/"
}

Beispiel 2 (E-Mail nicht gefunden):
{
  "nachname": "Muster",
  "vorname": "Anna",
  "institution": "Medizinische Universität Innsbruck, Institut für Humangenetik",
  "position": "nicht gefunden",
  "ort": "Innsbruck",
  "email": "nicht gefunden",
  "website": "https://www.i-med.ac.at/humgen/team.html.de"
}

Ausgabeformat:
Gib das Ergebnis ausschließlich als kompaktes JSON-Objekt zurück, genau
mit diesen Schlüsseln:

{
  "nachname": "...",
  "vorname": "...",
  "institution": "...",
  "position": "...",
  "ort": "...",
  "email": "...",
  "website": "..."
}

- Verwende "nicht gefunden" für Felder, die du trotz Recherche nicht
  belegen kannst.
- Verwende keine zusätzlichen Erklärtexte außerhalb des JSON.
"""


def find_detailed_contact(
    vorname: str,
    nachname: str,
    institution: str,
    ort: str,
    api_key: str,
) -> dict:
    """
    Nutzt Perplexity Sonar (web-grounded) zur detaillierten Recherche:
    Institution, Position, Ort, E-Mail, Website.
    """
    if not nachname and not vorname:
        return {
            "nachname": "",
            "vorname": "",
            "institution": "nicht gefunden",
            "position": "nicht gefunden",
            "ort": ort or "",
            "email": "nicht gefunden",
            "website": "nicht gefunden",
        }

    client = _perplexity_client(api_key)
    prompt = DETAILED_SEARCH_PROMPT.format(
        vorname=vorname or "",
        nachname=nachname or "",
        institution=institution or "",
        ort=ort or "",
    )

    try:
        resp = client.chat.completions.create(
            model="sonar",  # bei Bedarf auf "sonar-pro" umstellen
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du recherchierst berufliche Kontaktdaten von Personen "
                        "im Bereich Humangenetik und verwandten Fächern. "
                        "Nutze offizielle Uni-/Klinik-/Institutsseiten als Hauptquelle "
                        "und antworte ausschließlich mit dem angeforderten JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not m:
            raise ValueError("Kein JSON gefunden")
        data = json.loads(m.group(0))

        email = (data.get("email") or "").strip()
        if email and not EMAIL_RE.fullmatch(email):
            email = "nicht gefunden"

        # leichte Plausibilitätsprüfung Ort
        city = (data.get("ort") or "").strip()
        badge_city = (ort or "").strip()
        if badge_city and city and badge_city.lower() not in city.lower():
            # wenn abweichend, Badge-Stadt bevorzugen
            city = badge_city

        result = {
            "nachname": (data.get("nachname") or nachname or "").strip(),
            "vorname": (data.get("vorname") or vorname or "").strip(),
            "institution": (data.get("institution") or institution or "nicht gefunden").strip(),
            "position": (data.get("position") or "nicht gefunden").strip(),
            "ort": city,
            "email": email if email else "nicht gefunden",
            "website": (data.get("website") or "nicht gefunden").strip(),
        }
        return result
    except Exception:
        return {
            "nachname": nachname or "",
            "vorname": vorname or "",
            "institution": institution or "nicht gefunden",
            "position": "nicht gefunden",
            "ort": ort or "",
            "email": "nicht gefunden",
            "website": "nicht gefunden",
        }


# ──────────────────────────────────────────────────────────────
# 5. Hilfsfunktion: Badge-Basisdaten + Web-Recherche kombinieren
# ──────────────────────────────────────────────────────────────

def enrich_badge_data_with_web(badge_data: dict, api_key: str) -> dict:
    """
    Nimmt die von extract_badge_data gelieferten Felder und führt
    die detaillierte Web-Recherche durch. Gibt ein vollständig
    angereichertes Dict zurück, das direkt für den Excel-Export
    (detaillierte Liste) genutzt werden kann.
    """
    vorname = badge_data.get("Vorname", "")
    nachname = badge_data.get("Nachname", "")
    institution = badge_data.get("Institution", "")
    ort = badge_data.get("Ort", "")

    detailed = find_detailed_contact(
        vorname=vorname,
        nachname=nachname,
        institution=institution,
        ort=ort,
        api_key=api_key,
    )

    return {
        "Nachname": detailed["nachname"],
        "Vorname": detailed["vorname"],
        "Institution": detailed["institution"],
        "Position/Funktion": detailed["position"],
        "Ort": detailed["ort"],
        "E-Mail": detailed["email"],
        "Quelle": detailed["website"],
    }
