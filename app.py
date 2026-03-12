"""
Badge-Extraktor  ·  Streamlit PWA
Mobile-optimiert für iPhone  |  Perplexity Sonar API  |  Tesseract OCR
"""

import os
import tempfile
import time
from pathlib import Path

import streamlit as st
from PIL import Image

from extractor import extract_badge_data, ocr_image, extract_badge_fields, find_email
from excel_export import save_to_excel, load_records, COLUMNS

# ─── PWA + Mobile Meta-Tags ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Badge-Extraktor",
    page_icon="🪪",
    layout="centered",          # Auf Mobile besser als "wide"
    initial_sidebar_state="collapsed",
)

# Inject mobile-friendly meta + PWA manifest link
st.markdown("""
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Badge-Extraktor">
<meta name="theme-color" content="#01696F">
<style>
  /* Große Touch-Targets auf Mobile */
  .stButton > button {
    min-height: 52px !important;
    font-size: 1.05rem !important;
    border-radius: 12px !important;
  }
  /* Kompakterer Header auf Mobile */
  @media (max-width: 640px) {
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.2rem !important; }
    .block-container { padding-top: 1rem !important; padding-bottom: 5rem !important; }
  }
  /* Floating Action Area unten auf Mobile */
  .bottom-bar {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #F7F6F2; border-top: 1px solid #D4D1CA;
    padding: 0.75rem 1rem; z-index: 100;
  }
</style>
""", unsafe_allow_html=True)

# ─── Session-State ────────────────────────────────────────────────────────────
for key, default in [
    ("records", []),
    ("processed_files", set()),
    ("api_key", os.environ.get("PERPLEXITY_API_KEY", "")),
    ("step", "upload"),   # upload | processing | table | export
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Header ───────────────────────────────────────────────────────────────────
col_title, col_settings = st.columns([5, 1])
with col_title:
    st.title("🪪 Badge-Extraktor")
with col_settings:
    with st.popover("⚙️"):
        st.subheader("Einstellungen")
        api_key_input = st.text_input(
            "Perplexity API-Key",
            type="password",
            value=st.session_state.api_key,
            placeholder="pplx-...",
            help="perplexity.ai → API → API Keys",
        )
        if api_key_input != st.session_state.api_key:
            st.session_state.api_key = api_key_input

        do_email = st.toggle("E-Mail automatisch suchen", value=True)

        st.divider()
        if st.button("🗑️ Alle Einträge löschen", type="secondary", use_container_width=True):
            st.session_state.records = []
            st.session_state.processed_files = set()
            st.session_state.pop("xlsx_loaded", None)
            st.rerun()

        st.divider()
        # Bestehende Excel laden
        uploaded_xlsx = st.file_uploader("Bestehende .xlsx laden", type=["xlsx"])
        if uploaded_xlsx and not st.session_state.get("xlsx_loaded"):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded_xlsx.read())
                existing = load_records(tmp.name)
            if existing:
                st.session_state.records = existing
                st.session_state.xlsx_loaded = True
                st.success(f"{len(existing)} Einträge geladen.")

api_key = st.session_state.api_key

# API-Key-Hinweis (wenn nicht gesetzt)
if not api_key:
    st.warning("⚠️ Bitte zuerst den **Perplexity API-Key** über das ⚙️-Menü oben rechts eingeben.")
    st.markdown("[→ Hier API-Key erstellen](https://www.perplexity.ai/api)")
    st.stop()

# ─── Zähler-Leiste ────────────────────────────────────────────────────────────
if st.session_state.records:
    n_total = len(st.session_state.records)
    n_email = sum(1 for r in st.session_state.records if r.get("E-Mail"))
    c1, c2 = st.columns(2)
    c1.metric("Badges erfasst", n_total)
    c2.metric("Mit E-Mail", n_email)

st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_kamera, tab_tabelle, tab_export = st.tabs(["📷 Badge aufnehmen", "✏️ Bearbeiten", "💾 Export"])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: Kamera / Upload
# ══════════════════════════════════════════════════════════════════════════════
with tab_kamera:
    st.markdown("### Foto aufnehmen oder hochladen")

    # Auf iPhone: camera_input öffnet direkt die Kamera
    cam_img = st.camera_input(
        "Badge fotografieren",
        help="Auf dem iPhone öffnet dies direkt die Kamera.",
        label_visibility="collapsed",
    )

    st.markdown("<div style='text-align:center;color:#7A7974;font-size:0.85rem;margin:-0.5rem 0 0.75rem'>– oder –</div>", unsafe_allow_html=True)

    file_imgs = st.file_uploader(
        "Foto(s) aus Galerie wählen",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    # Alle Quellen zusammenführen
    to_process = []
    if cam_img:
        to_process.append(("kamera_aufnahme.jpg", cam_img))
    if file_imgs:
        for f in file_imgs:
            if f.name not in st.session_state.processed_files:
                to_process.append((f.name, f))

    if to_process:
        btn_label = f"▶️  {len(to_process)} Badge(s) verarbeiten"
        if st.button(btn_label, type="primary", use_container_width=True):
            for name, img_source in to_process:
                with st.status(f"Verarbeite {name} …", expanded=True) as status:

                    # Bild speichern
                    suffix = Path(name).suffix or ".jpg"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        if hasattr(img_source, "read"):
                            tmp.write(img_source.read())
                        else:
                            tmp.write(img_source.getvalue())
                        tmp_path = tmp.name

                    # Vorschau
                    st.image(Image.open(tmp_path), use_container_width=True)

                    # OCR
                    st.write("🔍 Tesseract liest Text …")
                    try:
                        ocr_text = ocr_image(tmp_path)
                        if ocr_text:
                            with st.expander("OCR-Rohtext"):
                                st.code(ocr_text, language=None)
                        else:
                            st.warning("Kein Text erkannt – bitte Fotoqualität prüfen.")
                    except Exception as e:
                        ocr_text = ""
                        st.error(f"OCR-Fehler: {e}")

                    # Feldextraktion
                    record = {c: "" for c in COLUMNS}
                    if ocr_text:
                        st.write("🤖 Perplexity strukturiert Daten …")
                        try:
                            record = extract_badge_fields(ocr_text, api_key)
                            st.success(
                                f"**{record['Nachname']}, {record['Vorname']}**  \n"
                                f"{record['Institution']}  ·  {record['Ort']}"
                            )
                        except Exception as e:
                            st.error(f"Perplexity-Fehler: {e}")

                    # E-Mail
                    if do_email and (record["Nachname"] or record["Vorname"]):
                        st.write("📧 E-Mail wird recherchiert …")
                        try:
                            email, source = find_email(
                                record["Vorname"], record["Nachname"],
                                record["Institution"], record["Ort"],
                                api_key=api_key,
                            )
                            record["E-Mail"] = email
                            record["Quelle"] = source
                            if email:
                                st.info(f"Gefunden: **{email}**")
                            else:
                                st.warning("Keine öffentliche E-Mail gefunden.")
                        except Exception as e:
                            st.warning(f"E-Mail-Suche: {e}")

                    status.update(label=f"✅ {record['Nachname']} {record['Vorname']}", state="complete")

                st.session_state.records.append(record)
                st.session_state.processed_files.add(name)
                os.unlink(tmp_path)
                time.sleep(0.2)

            st.balloons()
            st.rerun()

    elif not st.session_state.records:
        st.info("📸 Mach ein Foto vom Badge oder wähle ein Bild aus der Galerie.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Tabelle bearbeiten
# ══════════════════════════════════════════════════════════════════════════════
with tab_tabelle:
    if not st.session_state.records:
        st.info("Noch keine Einträge. Zuerst Badges fotografieren.")
    else:
        import pandas as pd

        df = pd.DataFrame(st.session_state.records, columns=COLUMNS)
        st.caption("Felder direkt antippen und korrigieren.")

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Nachname":    st.column_config.TextColumn("Nachname",    width="medium"),
                "Vorname":     st.column_config.TextColumn("Vorname",     width="medium"),
                "Institution": st.column_config.TextColumn("Institution", width="large"),
                "Ort":         st.column_config.TextColumn("Ort",         width="small"),
                "E-Mail":      st.column_config.TextColumn("E-Mail",      width="large"),
                "Quelle":      st.column_config.LinkColumn("Quelle",      width="small"),
            },
            hide_index=True,
        )

        if st.button("💾 Änderungen speichern", use_container_width=True):
            st.session_state.records = edited_df.to_dict(orient="records")
            st.success("Gespeichert.")

        # Einzelne E-Mail neu suchen
        st.divider()
        with st.expander("📧 E-Mail für eine Person neu suchen"):
            row_idx = st.number_input(
                "Zeile (1-basiert)", min_value=1,
                max_value=max(1, len(st.session_state.records)), step=1,
            )
            if st.button("🔍 Suchen", use_container_width=True):
                r = st.session_state.records[row_idx - 1]
                with st.spinner("Suche …"):
                    email, source = find_email(
                        r["Vorname"], r["Nachname"],
                        r["Institution"], r["Ort"],
                        api_key=api_key,
                    )
                if email:
                    st.session_state.records[row_idx - 1]["E-Mail"] = email
                    st.session_state.records[row_idx - 1]["Quelle"] = source
                    st.success(f"Gefunden: {email}")
                    st.rerun()
                else:
                    st.warning("Keine E-Mail gefunden.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: Export
# ══════════════════════════════════════════════════════════════════════════════
with tab_export:
    if not st.session_state.records:
        st.info("Noch keine Einträge.")
    else:
        st.markdown("### Excel herunterladen")

        filename = st.text_input("Dateiname", value="badges.xlsx")

        if st.button("📥 Excel erstellen", type="primary", use_container_width=True):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                out_path = tmp.name
            save_to_excel(st.session_state.records, out_path)
            with open(out_path, "rb") as f:
                xlsx_bytes = f.read()
            os.unlink(out_path)

            st.download_button(
                label="⬇️  Jetzt herunterladen",
                data=xlsx_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
