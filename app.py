import os
from pathlib import Path

import streamlit as st

from extractor import extract_badge_data, enrich_badge_data_with_web
from excel_export import export_detailed_list


st.set_page_config(page_title="Badge-Extraktor Humangenetik", layout="wide")

st.title("Badge-Extraktor – Humangenetik-Kontakte")
st.write(
    "Liest Namensbadges per OCR aus, recherchiert Institution, Funktion und "
    "E‑Mail über Perplexity Sonar und erzeugt eine detaillierte Kontaktliste "
    "für Excel."
)

# API-Key Eingabe
api_key = st.text_input(
    "Perplexity API Key",
    type="password",
    help="API-Key für die Perplexity Sonar API (OpenAI-kompatibel).",
)

uploaded_files = st.file_uploader(
    "Badge-Fotos hochladen (JPEG/PNG)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

start_button = st.button("Extraktion & Web-Recherche starten")


def _save_temp_file(uploaded_file) -> Path:
    temp_dir = Path("tmp_badges")
    temp_dir.mkdir(exist_ok=True)
    out_path = temp_dir / uploaded_file.name
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return out_path


if start_button:
    if not api_key:
        st.error("Bitte zuerst einen gültigen Perplexity API Key eingeben.")
    elif not uploaded_files:
        st.error("Bitte mindestens ein Badge-Foto hochladen.")
    else:
        results = []
        progress = st.progress(0)
        status = st.empty()

        for idx, uf in enumerate(uploaded_files, start=1):
            progress.progress(idx / len(uploaded_files))
            status.text(f"Verarbeite {uf.name} ({idx}/{len(uploaded_files)}) …")

            img_path = _save_temp_file(uf)

            # 1. Badge-Basisdaten (OCR + Strukturierung)
            badge_data = extract_badge_data(img_path, api_key=api_key)

            # 2. Detaillierte Web-Recherche (Institution, Position, E-Mail, Website)
            enriched = enrich_badge_data_with_web(badge_data, api_key=api_key)
            results.append(enriched)

        progress.progress(1.0)
        status.text("Fertig. Erzeuge Excel-Datei …")

        # Nur eine detaillierte Excel-Datei erzeugen
        output_path = Path("Humangenetik_Kontakte_Detailliert.xlsx")
        export_detailed_list(results, output_path)

        st.success("Detaillierte Excel-Datei wurde erstellt.")
        with open(output_path, "rb") as f:
            st.download_button(
                label="Detaillierte Kontaktliste herunterladen (Excel)",
                data=f,
                file_name=output_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        status.text("Fertig.")
