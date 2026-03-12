from pathlib import Path
from typing import List, Dict

import pandas as pd


COLUMNS_DETAILED = [
    "Nachname",
    "Vorname",
    "Institution",
    "Position/Funktion",
    "Ort",
    "E-Mail",
    "Quelle",  # Website / Profil- oder Team-URL
]


def export_detailed_list(rows: List[Dict], path: Path) -> None:
    """
    Erzeugt ausschließlich die detaillierte Kontaktliste
    im Excel-Format. Erwartet, dass jede Zeile bereits
    die Felder aus `enrich_badge_data_with_web` enthält.
    """
    df = pd.DataFrame(rows, columns=COLUMNS_DETAILED)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False)
