# 🪪 Badge-Extraktor

Fotografierte Konferenzbadges → automatische Texterkennung → Excel-Tabelle mit E-Mail-Recherche.

**Kein OpenAI nötig.** Verwendet ausschließlich:
- **Tesseract OCR** – lokal, kostenlos, kein API-Key
- **Perplexity Sonar API** – für Textstrukturierung und E-Mail-Recherche (Perplexity Pro reicht)

---

## Schnellstart

### 1. Tesseract installieren (einmalig)

**macOS:**
```bash
brew install tesseract tesseract-lang
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng
```

**Windows:**
Installer von https://github.com/UB-Mannheim/tesseract/wiki herunterladen und installieren.

### 2. Python-Abhängigkeiten

```bash
pip install -r requirements.txt
```

### 3. Perplexity API-Key

1. perplexity.ai aufrufen → Einstellungen → API → „API Keys" → neuen Key generieren
2. Key entweder in der App-Sidebar eingeben **oder** dauerhaft setzen:

```bash
export PERPLEXITY_API_KEY=pplx-...
```

Oder in einer `.env`-Datei im Projektordner:
```
PERPLEXITY_API_KEY=pplx-...
```

### 4. App starten

```bash
streamlit run app.py
```

Öffnet sich automatisch unter http://localhost:8501

---

## Ablauf

1. **Fotos hochladen** – JPG, PNG oder WEBP, mehrere auf einmal
2. **Tesseract OCR** liest den Text aus dem Badge-Foto (lokal, kein API-Call)
3. **Perplexity Sonar** strukturiert den OCR-Text → extrahiert Nachname, Vorname, Institution, Ort
4. **Perplexity Sonar** recherchiert die E-Mail-Adresse über Web-Suche
5. **Tabelle bearbeiten** – direkt im Browser korrigieren
6. **Excel herunterladen** – professionell formatierte .xlsx

---

## Kosten

| Schritt        | Tool              | Kosten             |
|----------------|-------------------|--------------------|
| OCR            | Tesseract (lokal) | kostenlos          |
| Strukturierung | Perplexity Sonar  | ~$0.001 pro Badge  |
| E-Mail-Suche   | Perplexity Sonar  | ~$0.001 pro Badge  |

Mit einem Perplexity Pro-Account sind die ersten Tokens pro Monat inklusive.

---

## Tipps für bessere Ergebnisse

- **Gut beleuchtete, gerade** Fotos liefern die besten OCR-Ergebnisse
- Falls OCR schlecht funktioniert: Rohtext im Expander prüfen und ggf. manuell korrigieren
- E-Mail nicht gefunden? Im "Tabelle bearbeiten"-Tab einzeln neu suchen lassen
