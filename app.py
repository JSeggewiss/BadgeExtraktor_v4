"""
Badge-Extraktor v4-mobile
Kombiniert:
- v2: mobile-optimierte Streamlit-PWA mit editierbarer Tabelle
- v4: detaillierte Web-Recherche (Institution, Position, E-Mail, Website)
"""

import os
import tempfile
import time
from pathlib import Path

import streamlit as st
from PIL import Image

from extractor import (
    extract_badge_data,
    enrich_badge_data_with_web,
)
from excel_export import save_to_excel, load_records, COLUMNS

# ─── PWA + Mobile Meta-Tags ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Badge-Extraktor",
    page_icon="🪪",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Badge-Extraktor">
<meta name="theme-color" content="#01696F">
<style>
  .stButton > button {
    min-height: 52px !important;
    font-size: 1.05rem !important;
    border-radius: 12px !important;
  }
  @media (max-width: 640px) {
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.15rem !important; }
    .block-container { padding-top: 0.8rem !important; padding-bottom: 5rem !important; }
  }
</style>
""",
    unsafe_allow_html=True,
)

# ─── Session-State ────────────────────────────────────────────────────────────
for key, default in [
    ("records", []),              # Liste von Dicts mit COLUMNS
    ("processed_files", set()),
    ("api_key", os.environ.get("PERPLEXITY_API_KEY", "")),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Header ───────────────────────────────────────────────────────────────────
col_title, col_settings = st.columns([5, 1])
with col_title:
    st.title("🪪 Badge-Extraktor")
    st.caption("Mobile · Perplexity Sonar · Tesseract OCR · detaillierte Kontakte")
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

        st.divider()
        st.caption("Web-Recherche")
        # v4: immer detailliert, daher nur Schalter für "automatisch nach Aufnahme"
        auto_enrich = st.toggle(
            "Nach Aufnahme automatisch detailliert recherchieren",
            value=True,
            help="Führt sofort die Web-Recherche (Institution, Position, E-Mail) durch.",
            key="auto_enrich",
        )

        st.divider()
        if st.button("🗑️ Alle Einträge löschen", type="secondary", use_container_width=True):
            st.session_state.records = []
            st.session_state.processed_files = set()
            st.session_state.pop("xlsx_loaded", None)
            st.rerun()

        st.divider()
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

if not api_key:
    st.warning("⚠️ Bitte zuerst den **Perplexity API-Key** über das ⚙️-Menü oben rechts eingeben.")
    st.markdown("[→ Hier API-Key erstellen](https://www.perplexity.ai/api)")
    st.stop()

# ─── Zähler-Leiste ────────────────────────────────────────────────────────────
if st.session_state.records:
    n_total = len(st.session_state.records)
    n_email = sum(1 for r in st.session_state.records if r.get("E-Mail") and r["E-Mail"] != "nicht gefunden")
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

    cam_img = st.camera_input(
        "Badge fotografieren",
        label_visibility="collapsed",
    )

    st.markdown(
        "<div style='text-align:center;color:#7A7974;font-size:0.85rem;margin:-0.5rem 0 0.75rem'>"
        "– oder –</div>",
        unsafe_allow_html=True,
    )

    file_imgs = st.file_uploader(
        "Foto(s) aus Galerie wählen",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    # Quellen zusammenführen, Duplikate ausschließen
    to_process = []
    if cam_img:
        to_process.append(("kamera_aufnahme.jpg", cam_img))
    if file_imgs:
        for f in file_imgs:
            if f.name not in st.session_state.processed_files:
                to_process.append((f.name, f))

    if to_process:
        if st.button(
            f"▶️  {len(to_process)} Badge(s) verarbeiten",
            type="primary",
            use_container_width=True,
        ):
            for name, img_source in to_process:
                with st.status(f"Verarbeite {name} …", expanded=True) as status:

                    # Bild temporär speichern
                    suffix = Path(name).suffix or ".jpg"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        data = img_source.read() if hasattr(img_source, "read") else img_source.getvalue()
                        tmp.write(data)
                        tmp_path = tmp.name

                    # Vorschau
                    st.image(Image.open(tmp_path), use_container_width=True)

                    # ── Schritt 1: OCR + Badge-Basisdaten ─────────────────
                    st.write("🔍 Schritt 1 / 2 — OCR & Strukturierung …")
                    badge_record = extract_badge_data(tmp_path, api_key=api_key)
                    if badge_record.get("Nachname") or badge_record.get("Vorname"):
                        st.success(
                            f"**{badge_record['Nachname']}, {badge_record['Vorname']}**  \n"
                            f"{badge_record['Institution'] or '—'}  ·  {badge_record['Ort'] or '—'}"
                        )
                    else:
                        st.warning("Kein Name erkannt – bitte ggf. manuell in der Tabelle korrigieren.")

                    # ── Schritt 2: Detaillierte Web-Recherche ─────────────
                    if st.session_state.auto_enrich:
                        st.write("🌐 Schritt 2 / 2 — Detaillierte Web-Recherche …")
                        try:
                            enriched = enrich_badge_data_with_web(badge_record, api_key=api_key)
                            record = enriched
                            if record.get("E-Mail") and record["E-Mail"] != "nicht gefunden":
                                st.info(f"📧 Gefunden: **{record['E-Mail']}**")
                            else:
                                st.warning("Keine öffentliche E-Mail gefunden.")
                        except Exception as e:
                            st.warning(f"Web-Recherche: {e}")
                            # Fallback: nur Badge-Daten übernehmen
                            record = {
                                "Nachname": badge_record.get("Nachname", ""),
                                "Vorname": badge_record.get("Vorname", ""),
                                "Institution": badge_record.get("Institution", ""),
                                "Position/Funktion": "",
                                "Ort": badge_record.get("Ort", ""),
                                "E-Mail": "",
                                "Quelle": "",
                            }
                    else:
                        st.write("🌐 Schritt 2 / 2 — Web-Recherche übersprungen.")
                        record = {
                            "Nachname": badge_record.get("Nachname", ""),
                            "Vorname": badge_record.get("Vorname", ""),
                            "Institution": badge_record.get("Institution", ""),
                            "Position/Funktion": "",
                            "Ort": badge_record.get("Ort", ""),
                            "E-Mail": "",
                            "Quelle": "",
                        }

                    status.update(
                        label=f"✅ {record['Nachname']} {record['Vorname']} — {record['Institution']}",
                        state="complete",
                    )

                st.session_state.records.append(record)
                st.session_state.processed_files.add(name)
                os.unlink(tmp_path)
                time.sleep(0.2)

            st.balloons()
            st.rerun()

    elif not st.session_state.records:
        st.info("📸 Mach ein Foto vom Badge oder wähle ein Bild aus der Galerie.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Tabelle bearbeiten + selektive Neu-Recherche
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
                "Position/Funktion": st.column_config.TextColumn("Position/Funktion", width="large"),
                "Ort":         st.column_config.TextColumn("Ort",         width="small"),
                "E-Mail":      st.column_config.TextColumn("E-Mail",      width="large"),
                "Quelle":      st.column_config.LinkColumn("Quelle",      width="small"),
            },
            hide_index=True,
        )

        if st.button("💾 Änderungen speichern", use_container_width=True):
            records = edited_df.to_dict(orient="records")
            st.session_state.records = records
            st.success("Gespeichert.")

        st.divider()
        st.markdown("### Selektive Neu-Recherche")

        with st.expander("🌐 Institution, Position & Ort für eine Person neu recherchieren"):
            row_idx = st.number_input(
                "Zeile (1-basiert)", min_value=1,
                max_value=max(1, len(st.session_state.records)), step=1, key="enrich_row",
            )
            if st.button("🔍 Detaillierte Web-Recherche", use_container_width=True, key="btn_enrich"):
                r = st.session_state.records[row_idx - 1]
                with st.spinner("Suche …"):
                    badge_like = {
                        "Nachname": r.get("Nachname", ""),
                        "Vorname": r.get("Vorname", ""),
                        "Institution": r.get("Institution", ""),
                        "Ort": r.get("Ort", ""),
                    }
                    detailed = enrich_badge_data_with_web(badge_like, api_key=api_key)
                st.session_state.records[row_idx - 1] = detailed
                st.success(
                    f"Aktualisiert: {detailed['Nachname']} {detailed['Vorname']} · "
                    f"{detailed['Institution']} · {detailed['Ort']}"
                )
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: Export
# ══════════════════════════════════════════════════════════════════════════════
with tab_export:
    if not st.session_state.records:
        st.info("Noch keine Einträge.")
    else:
        st.markdown("### Excel herunterladen")

        c1, c2 = st.columns(2)
        c1.metric("Einträge gesamt", len(st.session_state.records))
        c2.metric(
            "Mit E-Mail",
            sum(1 for r in st.session_state.records if r.get("E-Mail") and r["E-Mail"] != "nicht gefunden"),
        )

        filename = st.text_input("Dateiname", value="badges_detailliert.xlsx")

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
