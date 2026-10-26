"""Texte, Konstanten und Vorlagen der Oberfläche – alles, was nur Daten ist.

Zweck:   Sammelt Stylesheet, Logo, Schriften, Spaltenlisten, Kurztexte, SVG-Symbole und das JavaScript des
         Breitengriffs an einer Stelle. So bleiben die Dateien, die ein Blatt aufbauen, kurz und lesbar.
Eingabe: ui/theme.css und assets/logo.svg (werden beim Import gelesen)
Ausgabe: Konstanten, die ui/page.py, die Kopfzeile (header.py) und die Blätter (sheet_*.py, panel.py, bottom_bar.py,
         detail.py) importieren
"""

from pathlib import Path

from config import QUALITIES

THEME_CSS = (Path(__file__).parent / "theme.css").read_text(encoding="utf-8")
LOGO_SVG = (Path(__file__).parent.parent / "assets" / "logo.svg").read_text(encoding="utf-8")
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700'
         '&family=IBM+Plex+Mono:wght@400;500;600&display=swap">')

# --- Leiste links und Blätter --------------------------------------------------------------
STEPS = [("datei", "01", "DATEI"), ("setup", "02", "SETUP"), ("regeln", "03", "REGELN"), ("ausgabe", "04", "AUSGABE")]
DROPZONE_TEXT = "IFC-Datei hierher ziehen oder klicken"
EMPTY_SHEET_TEXT = "Zuerst eine IFC-Datei laden."
# Breite des offenen Blattes je Kapitel (für die Legende im Viewer); 03 hängt vom Tab ab
SHEET_WIDTH = {"datei": "408px", "ausgabe": "408px", "pruefen": "480px", "verlauf": "640px",
               "regeln": "var(--breite-03-klassen)", "regeln-bauteile": "var(--breite-03-bauteile)"}

# --- Status, Aktionen, Matrix ----------------------------------------------------------------
STATUS_CLASS_NAME = {"druckbar": "ok", "kritisch": "warn", "nicht_druckbar": "err", "nicht_gedruckt": "skip"}
# (Status, Kürzel, CSS-Klasse) – Reihenfolge überall gleich
MATRIX_COLUMNS = [("druckbar", "OK", "ok"), ("kritisch", "Prüfen", "warn"), ("nicht_druckbar", "Nicht dr.", "err"),
                  ("nicht_gedruckt", "Weg", "skip")]
# (CSS-Klasse, Kürzel, Langtext) für die Legenden in Kopfzeile und Viewer
LEGEND = (("ok", "OK", "druckbar"), ("warn", "Prüfen", "kritisch"), ("err", "Nicht dr.", "nicht druckbar"),
          ("skip", "Weg", "nicht gedruckt"))

# --- 02 Setup (Kopfzeile, Variante «Schritte») -------------------------------------------------
QUALITY_NOTE = (f"Fein = {QUALITIES['fein']:g} mm Voxel, Entwurf = {QUALITIES['entwurf']:g} mm, "
                "Auto = fein, bei grossen Modellen Entwurf")
ALIGN_NOTE = "Automatisch ausrichten: dominante Wandrichtung achsparallel"
CONNECTOR_NOTE = "Zapfen und Löcher zwischen den Geschossteilen"
# Öffnungen: Knopftext und Piktogramm 44 × 18 px aus Rechtecken (links, oben, Breite, Höhe, ausgespart)
OPENING_CAPTION = {"geschlossen": "voll", "vertieft": "vertieft", "ausgeschnitten": "offen"}
OPENING_PICTO = {"geschlossen": [(0, 5, 44, 8, False)],
                 "vertieft": [(0, 5, 44, 8, False), (12, 5, 20, 2, True), (12, 11, 20, 2, True)],
                 "ausgeschnitten": [(0, 5, 14, 8, False), (30, 5, 14, 8, False)]}
SETUP_SVG = ('<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5">'
             '<line x1="2" y1="4" x2="12" y2="4"/><line x1="2" y1="10" x2="12" y2="10"/>'
             '<circle cx="5" cy="4" r="1.8" fill="currentColor"/><circle cx="9" cy="10" r="1.8" fill="currentColor"/></svg>')
MATRIX_SVG = ('<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">'
              '<rect x="1.5" y="1.5" width="4.5" height="4.5" rx="1"/><rect x="8" y="1.5" width="4.5" height="4.5" rx="1"/>'
              '<rect x="1.5" y="8" width="4.5" height="4.5" rx="1"/><rect x="8" y="8" width="4.5" height="4.5" rx="1"/></svg>')

# --- 03 Regeln › IFC-Klassen: Gruppen nach Kategorie der Regel ---------------------------------------
GROUP_OF = {"Wand": "TRAGWERK", "Decke": "TRAGWERK", "Dach": "TRAGWERK", "Stütze": "TRAGWERK", "Träger": "TRAGWERK",
            "Fundament": "TRAGWERK", "Treppe": "ERSCHLIESSUNG", "Geländer": "ERSCHLIESSUNG",
            "Verglasung": "AUSBAU · ÖFFNUNGEN", "Öffnung": "AUSBAU · ÖFFNUNGEN", "Ausbau": "AUSBAU · ÖFFNUNGEN",
            "Fassade": "AUSBAU · ÖFFNUNGEN"}   # alles andere: "SONSTIGES"
GROUP_ORDER = ("TRAGWERK", "ERSCHLIESSUNG", "AUSBAU · ÖFFNUNGEN", "SONSTIGES")
GROUP_WITHOUT_RULE = "OHNE EIGENE REGEL"

# --- 03 Bauteile: Tabellenspalten und Zeilenvorlage (Vue) -------------------------------------------
COLUMNS = [
    {"name": "name", "label": "Name", "field": "name", "align": "left", "headerStyle": "width: auto"},
    {"name": "ifc_class", "label": "IFC-Klasse", "field": "ifc_class", "align": "left", "headerStyle": "width: 150px"},
    {"name": "storey", "label": "Gesch.", "field": "storey", "align": "left", "headerStyle": "width: 54px"},
    {"name": "thickness", "label": "mm", "field": "thickness", "align": "left", "headerStyle": "width: 50px"},
    {"name": "status", "label": "Status", "field": "status", "align": "left", "headerStyle": "width: 124px"},
    {"name": "rule", "label": "Regel", "field": "rule", "align": "left", "headerStyle": "width: 80px"},
]
NO_SELECTION_TEXT = "Bauteil anklicken oder im Modell wählen – das Detail erscheint rechts."
# Ausnahme für gewählte Bauteile: (Aktion, Knopftext); None = wie Regel
EXCEPTION_BUTTONS = (("behalten", "drucken"), ("entfernen", "nicht drucken"), (None, "wie Regel"))
STATUS_SLOT = r'''<q-td key="status" :props="props"><span :class="'status-dot ' + ({druckbar:'ok', kritisch:'warn',
    nicht_druckbar:'err', nicht_gedruckt:'skip'})[props.row.status]">{{ props.row.status.replace('_', ' ') }}</span><span
    v-if="props.row.geometry !== 'ok'" class="geo-warn">{{ props.row.geometry === 'fehlt'
    ? 'keine Geometrie' : 'defekt' }}</span></q-td>'''
# Ganze Zeile: Gruppenkopf «Klasse n» vor der ersten Zeile einer IFC-Klasse, dann die Bauteilzeile.
# Der Gruppenkopf zählt nicht als Zeile der virtuellen Liste (q-virtual-scroll--skip) und spannt über alle Spalten
# (colspan = Spalten + Auswahl; «100%» gälte als 100 Spalten und zerlegt das feste Spaltenraster). Den Zeilenklick fängt
# ROW_CLICK_JS an der Tabelle ab (data-guid): $parent.$emit erreicht in der virtuellen Liste die Tabelle nicht.
BODY_SLOT = r'''
    <q-tr v-if="props.row.group_head" class="gruppe q-virtual-scroll--skip"><q-td :colspan="props.cols.length + 1"><span>{{
      props.row.group_head }}</span><small>{{ props.row.group_count }}</small></q-td></q-tr>
    <q-tr :props="props" :class="'zeile' + (props.selected ? ' selected' : '')" :data-guid="props.row.guid">
      <q-td auto-width class="auswahl"><q-checkbox dense size="xs" v-model="props.selected" /></q-td>
      <q-td key="name" :props="props" class="name" :title="props.row.name">{{ props.row.name }}</q-td>
      <q-td key="ifc_class" :props="props" class="klasse">{{ props.row.ifc_class }}</q-td>
      <q-td key="storey" :props="props">{{ props.row.storey }}</q-td>
      <q-td key="thickness" :props="props" class="dicke">{{ props.row.thickness ?? '–' }}</q-td>
      ''' + STATUS_SLOT + r'''
      <q-td key="rule" :props="props" :class="props.row.is_exception ? 'ausnahme' : 'regel'">{{ props.row.rule }}</q-td>
    </q-tr>'''

# Klick auf eine Bauteilzeile (nicht auf das Kästchen): GUID und Zusatztaste an den Server
ROW_CLICK_JS = """(e) => {
  const tr = e.target.closest('tr[data-guid]');
  if (tr && !e.target.closest('.auswahl')) emit({guid: tr.dataset.guid, multi: e.ctrlKey || e.metaKey || e.shiftKey});
}"""

# --- 04 Ausgabe, 05 Prüfen, untere Leiste ---------------------------------------------------------
CHECK_CATEGORIES = [("regeln", "Klassen ohne eigene Regel"), ("geometry", "Defekte Geometrie"),
                    ("storeys", "Doppelte Geschosse"), ("ausreisser", "Ausreisser"), ("umgebung", "Umgebung"),
                    ("georeferenz", "Georeferenz")]
# Downloads des FDM-Ziels: Schlüssel aus config.OutputTarget.exports → (Knopftext, Tooltip)
DOWNLOADS = {"stl": ("Gebäude", ".stl download des kompletten Gebäudes"),
             "zip": ("Geschosse", ".stl download der einzelnen Geschosse als .zip"),
             "plate": ("Platziert", ".stl download der einzelnen Geschosse in einer Druckplattenoptimierten Datei")}
STALE_NOTE = "Veraltet – zuerst neu erzeugen"

# --- Verlauf (Exportverlauf aus der Datenbank): Spaltenname und Überschrift -----------------------------
HISTORY_COLUMNS = [("date", "Datum"), ("ifc_name", "Datei"), ("scale", "Massstab"), ("ruleset_name", "Regelset"),
                   ("mode", "Qualität"), ("element_count", "Bauteile"), ("part_count", "Teile"),
                   ("windows", "Fenster"), ("doors", "Türen"), ("connectors", "Verbinder"),
                   ("filament_g", "Filament (g)"), ("cost_chf", "Kosten"), ("time_h", "Zeit (h)")]

# --- Ansichtsleiste und Modellkarte ----------------------------------------------------------------
# Ansichten des Viewers: (Name, Knopftext, Tooltip)
VIEW_MODES = (("ifc", "IFC", "IFC-Modell, Geschosse eingefärbt"), ("status", "STAT", "Druckbarkeit je Bauteil"),
              ("stl", "STL", "Erzeugtes Druckmodell"))
TIGHT_THRESHOLD = 0.9        # Anteil am Bauraum: darüber «knapp» (orange), über 1 «zu gross» (rot)
FIT_MARK = {"ok": "passt", "knapp": "knapp", "gross": "zu gross"}

# --- Breitengriff rechts neben 03 -----------------------------------------------------------------
WIDTH_03 = {"klassen": (520, 400, 720), "bauteile": (700, 500, 900)}   # je Tab: Start, min, max [px]
# Breite des aktiven Tabs live setzen (Hilfslinien bei min/max, Badge mit der Breite), am Ende an den Server melden
HANDLE_JS = f"""(e) => {{
  const griff = e.target.closest('.griff'), blatt = griff.closest('.sheet'), app = griff.closest('.app');
  const tab = blatt.classList.contains('tab-bauteile') ? 'bauteile' : 'klassen';
  const [min, max] = tab === 'bauteile' ? [{WIDTH_03['bauteile'][1]}, {WIDTH_03['bauteile'][2]}]
                                        : [{WIDTH_03['klassen'][1]}, {WIDTH_03['klassen'][2]}];
  const x0 = e.clientX, w0 = blatt.offsetWidth;
  griff.classList.add('zieht'); e.preventDefault();
  const linie = (x) => {{ const d = document.createElement('div'); d.className = 'griff-linie'; d.style.left = x + 'px';
    blatt.appendChild(d); return d; }};
  const hilfen = [linie(min), linie(max)], badge = document.createElement('div');
  badge.className = 'griff-badge'; blatt.appendChild(badge);
  const breite = (w) => {{ app.style.setProperty('--breite-03-' + tab, w + 'px'); badge.textContent = '⇔ ' + w + ' px'; }};
  breite(w0);
  const zieh = (m) => breite(Math.round(Math.max(min, Math.min(max, w0 + m.clientX - x0))));
  const los = () => {{ document.removeEventListener('mousemove', zieh); document.removeEventListener('mouseup', los);
    griff.classList.remove('zieht'); hilfen.forEach((h) => h.remove()); badge.remove();
    emitEvent('breite_03_' + tab, blatt.offsetWidth); }};
  document.addEventListener('mousemove', zieh); document.addEventListener('mouseup', los);
}}"""

# --- SVG-Symbole ------------------------------------------------------------------------------------
# Geschosse auseinander: ein schlichter Doppelpfeil
EXPLODE_SVG = ('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" '
               'stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M7.5 7.5 12 3l4.5 4.5M7.5 16.5 12 21l4.5-4.5"/>'
               '</svg>')
DROPZONE_SVG = ('<svg aria-hidden="true"><rect x="0.75" y="0.75" rx="9.5" ry="9.5" fill="none" stroke-width="1.5" '
                'stroke-dasharray="9 6"/></svg>')
