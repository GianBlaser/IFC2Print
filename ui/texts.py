"""Texte, Konstanten und Vorlagen der Oberfläche – alles, was nur Daten ist.

Zweck:   Sammelt Stylesheet, Logo, Schriften, Spaltenlisten, Kurztexte, SVG-Symbole und das JavaScript des
         Breitengriffs an einer Stelle. So bleiben die Dateien, die ein Blatt aufbauen, kurz und lesbar.
Eingabe: ui/theme.css und assets/logo.svg (werden beim Import gelesen)
Ausgabe: Konstanten, die ui/page.py und die Blätter (sheet_*.py, panel.py, bottom_bar.py, detail.py) importieren
"""

from pathlib import Path

THEME_CSS = (Path(__file__).parent / "theme.css").read_text(encoding="utf-8")
LOGO_SVG = (Path(__file__).parent.parent / "assets" / "logo.svg").read_text(encoding="utf-8")
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700'
         '&family=IBM+Plex+Mono:wght@400;500;600&display=swap">')

# --- Leiste links und Blätter --------------------------------------------------------------
STEPS = [("datei", "01", "DATEI"), ("setup", "02", "SETUP"), ("regeln", "03", "REGELN"), ("ausgabe", "04", "AUSGABE")]
DROPZONE_TEXT = "IFC-Datei hierher ziehen oder klicken"
EMPTY_SHEET_TEXT = "Zuerst eine IFC-Datei laden."

# --- Status, Aktionen, Matrix ----------------------------------------------------------------
STATUS_CLASS_NAME = {"druckbar": "ok", "kritisch": "warn", "nicht_druckbar": "err"}
MATRIX_COLUMNS = [("druckbar", "OK", "ok"), ("kritisch", "Prüfen", "warn"), ("nicht_druckbar", "Nicht dr.", "err"),
                  ("nicht_gedruckt", "Weg", "skip")]
STATUS_SHORT = {"druckbar": "ok", "kritisch": "prüfen", "nicht_druckbar": "nicht dr.", "nicht_gedruckt": "weg",
                "geometry": "Geometrie-Probleme"}
ACTION_SHORT = {"behalten": "beh.", "verdicken": "verd.", "fuellen": "füll.", "band": "band", "entfernen": "entf."}

# --- 02 Setup --------------------------------------------------------------------------------
# Kurzbeschreibung je Massstab unter den Segmenten
SCALE_NOTE = {
    "1:500": "Volumenmodell: Wände min. 0.8 mm, Laibung nur aussen, keine Treppen und Geländer, keine Steckverbinder. Auskragungen brauchen Stützmaterial.",
    "1:200": "Standard: Wände min. 1.2 mm, Treppen, Geländer als 0.8-mm-Band.",
    "1:100": "Detail: tiefere Laibungen (0.8 mm), Dachaufbau.",
    "1:50": "Ausschnitt: einzelne Geschosse wählen; Qualität «auto» wechselt bei grossen Modellen auf 0.8 mm.",
}

# --- 03 Bauteile: Tabellenspalten und Zellvorlagen (Vue) -------------------------------------------
COLUMNS = [
    {"name": "name", "label": "Name", "field": "name", "align": "left", "classes": "name", "sortable": True},
    {"name": "storey", "label": "Geschoss", "field": "storey", "align": "left", "sortable": True},
    {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
    {"name": "thickness", "label": "mm", "field": "thickness", "sortable": True, "classes": "mono"},
    {"name": "is_printed", "label": "Druck", "field": "is_printed", "align": "center", "sortable": True},
]
NO_SELECTION_TEXT = "Bauteil anklicken oder im Modell wählen"
# Ausnahme für gewählte Bauteile: (Aktion, Knopftext); None = wie Regel
EXCEPTION_BUTTONS = (("behalten", "drucken"), ("entfernen", "nicht drucken"), (None, "wie Regel"))
STATUS_SLOT = r'''
    <q-td :props="props"><span :class="'status-dot ' + ({druckbar:'ok', kritisch:'warn',
    nicht_druckbar:'err', nicht_gedruckt:'skip'})[props.value]">{{ props.value.replace('_', ' ') }}</span><span
    v-if="props.row.geometry !== 'ok'" class="geo-warn">{{ props.row.geometry === 'fehlt'
    ? 'keine Geometrie' : 'defekt' }}</span></q-td>'''
PRINT_SLOT = r'''
    <q-td :props="props" @click.stop><q-toggle dense size="sm" :model-value="props.row.is_printed"
    @update:model-value="$parent.$emit('toggle_print', props.row.guid, $event)" /></q-td>'''

# --- 05 Prüfen ---------------------------------------------------------------------------------
CHECK_CATEGORIES = [("regeln", "Klassen ohne eigene Regel"), ("geometry", "Defekte Geometrie"),
                    ("storeys", "Doppelte Geschosse"), ("ausreisser", "Ausreisser"), ("umgebung", "Umgebung"),
                    ("georeferenz", "Georeferenz")]

# --- Verlauf (Exportverlauf aus der Datenbank): Spaltenname und Überschrift -----------------------------
HISTORY_COLUMNS = [("date", "Datum"), ("ifc_name", "Datei"), ("scale", "Massstab"), ("ruleset_name", "Regelset"),
                   ("mode", "Qualität"), ("element_count", "Bauteile"), ("part_count", "Teile"),
                   ("windows", "Fenster"), ("doors", "Türen"), ("connectors", "Verbinder"),
                   ("filament_g", "Filament (g)"), ("cost_chf", "Kosten"), ("time_h", "Zeit (h)")]

# --- Panel rechts: Ansichtsleiste, Legende und Modell im Druckbett ----------------------------------------
# Ansichten des Viewers: (Name, Knopftext, Tooltip)
VIEW_MODES = (("ifc", "IFC", "IFC-Modell, Geschosse eingefärbt"), ("status", "STAT", "Druckbarkeit je Bauteil"),
              ("stl", "STL", "Erzeugtes Druckmodell"))
LEGEND = (("ok", "druckbar"), ("warn", "kritisch"), ("err", "nicht druckbar"), ("skip", "nicht gedruckt"))
BED_AXES = ("X · Breite", "Y · Tiefe", "Z · Höhe")
TIGHT_THRESHOLD = 0.9        # Anteil am Bauraum: darüber «knapp» (orange), über 1 «zu gross» (rot)
FIT_MARK = {"ok": "✓ passt", "knapp": "⚠ knapp", "gross": "✗ zu gross"}
FIT_NOTE = {"ok": "", "knapp": " · knapp", "gross": " · zu gross"}

# --- Breitengriff am rechten Rand von 03 -----------------------------------------------------------
WIDTH_03 = (520, 400, 720)    # Blatt 03: Start, min, max [px]
# Breite live setzen, am Ende an den Server melden (app.storage.user)
HANDLE_JS = f"""(e) => {{
  const griff = e.target, blatt = griff.closest('.sheet'), x0 = e.clientX, w0 = blatt.offsetWidth;
  griff.classList.add('zieht'); e.preventDefault();
  const zieh = (m) => blatt.style.setProperty('--breite-03',
    Math.max({WIDTH_03[1]}, Math.min({WIDTH_03[2]}, w0 + m.clientX - x0)) + 'px');
  const los = () => {{ document.removeEventListener('mousemove', zieh); document.removeEventListener('mouseup', los);
    griff.classList.remove('zieht'); emitEvent('breite_03', blatt.offsetWidth); }};
  document.addEventListener('mousemove', zieh); document.addEventListener('mouseup', los);
}}"""

# --- SVG-Symbole ------------------------------------------------------------------------------------
ARROW_SVG = ('<svg viewBox="0 0 10 32"><path d="M8 2 2 16l6 14" fill="none" stroke="#C9CDD3" stroke-width="1.4" '
             'stroke-linecap="round" stroke-linejoin="round"/></svg>')
# Geschosse auseinander: ein schlichter Doppelpfeil
EXPLODE_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
               'stroke-linejoin="round"><path d="M12 3v18M7.5 7.5 12 3l4.5 4.5M7.5 16.5 12 21l4.5-4.5"/></svg>')
