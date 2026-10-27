"""SQLite-Datenbank für Regeln, Druckerprofile, Material und Exportverlauf.

Zweck:   speichert, was der Nutzer einstellt (eigene Regeln je Massstab) und was er erzeugt hat.
Eingabe: Pfad der Datenbankdatei; db/schema.sql und die Seed-CSVs in db/seed/
Ausgabe: Klasse Database mit Lese- und Schreibmethoden (Zeilen als dict)

Beim Start wird das Schema angelegt und die Seed-CSVs in db/seed/ werden
eingespielt. INSERT OR IGNORE ergänzt fehlende Standardeinträge, ohne
Änderungen des Nutzers zu überschreiben. Ausnahme: Die Massstab-Parameter (Tabelle scale) ändert der Nutzer nicht;
sie werden jedes Mal aus massstaebe.csv übernommen, damit die CSV die einzige Quelle bleibt.
Die regeln.db selbst wird nicht eingecheckt.
"""

import csv
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from config import SCALES
from core.analysis.ruleset import check_action, LEGACY_RULE_SETS, seed_rules

_HERE = Path(__file__).parent
DEFAULT_PATH = _HERE / "regeln.db"
# Die Regeln kommen nicht direkt aus regeln.csv, sondern je Massstab aufgelöst (ruleset.seed_rules)
_SEEDS = {"scale": "massstaebe.csv", "printer_profile": "profile.csv", "material": "material.csv"}
_LOG = logging.getLogger(__name__)
# Frühere Standardregeln (Schlüssel → Standardaktion), die eine allgemeinere Regel ersetzt hat. Unverändert
# (= kein Entscheid des Nutzers) werden sie gelöscht, damit sie nicht als «Eigene Regel» stehen bleiben.
_RETIRED_RULES = {"IfcFlowTerminal": "entfernen"}         # Okt. 2026: IfcDistributionElement
# Seed-Spalten ohne Gegenstück in der Datenbank: die Begründung gehört zum Standard (ruleset.rule_reason)
_CSV_ONLY = {"reason"}
# Deutsche Tabellen- und Spaltennamen bis Oktober 2026 → heutige Namen (für _migrate_to_english)
_GERMAN_NAMES = {
    "regel": ("rule", {"regelset": "ruleset_name", "ifc_klasse": "ifc_class_name", "aktion": "action",
                       "kategorie": "category"}),
    "massstab": ("scale", {"regelset": "ruleset_name", "zahl": "denominator",
                           "mindestdicke_wand_mm": "min_thickness_wall_mm",
                           "mindestdicke_gelaender_mm": "min_thickness_railing_mm",
                           "laibungstiefe_mm": "reveal_depth_mm", "mindestkern_laibung_mm": "min_core_reveal_mm",
                           "qualitaeten": "qualities", "qualitaet_default": "quality_default",
                           "verbinder_erlaubt": "connectors_allowed", "fenster_default": "window_default",
                           "tuer_default": "door_default"}),
    "drucker_profil": ("printer_profile", {"duese_mm": "nozzle_mm", "layer_hoehe_mm": "layer_height_mm",
                                           "bauraum_x_mm": "build_volume_x_mm", "bauraum_y_mm": "build_volume_y_mm",
                                           "bauraum_z_mm": "build_volume_z_mm", "mindestwand_mm": "min_wall_mm",
                                           "spiel_mm": "clearance_mm"}),
    "material": ("material", {"dichte_g_cm3": "density_g_cm3", "preis_chf_kg": "price_chf_kg"}),
    "exportlauf": ("export_run", {"datum": "date", "massstab": "scale", "profil_id": "profile_id",
                                  "regelset": "ruleset_name", "modus": "mode", "fenster_fuellen": "window_fill",
                                  "anzahl_teile": "part_count", "anzahl_bauteile": "element_count",
                                  "fenster": "windows", "tuer": "doors", "verbinder": "connectors",
                                  "zeit_h": "time_h", "kosten_chf": "cost_chf"}),
}


class Database:
    """Dünne, threadsichere Hülle um eine SQLite-Verbindung."""

    def __init__(self, file_path: str | Path = DEFAULT_PATH):
        # Die App greift aus mehreren Threads zu → eine Verbindung, serialisiert per Lock.
        self._conn = sqlite3.connect(str(file_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._migrate_to_english()
            # Altlast: frühere UI-Version speicherte die ungültige Aktion «drucken».
            if self._table_exists("rule"):
                self._conn.execute("UPDATE rule SET action = 'behalten' WHERE action = 'drucken'")
            self._conn.executescript((_HERE / "schema.sql").read_text(encoding="utf-8"))
            self._migrate_rules()
            self._add_columns("export_run", {"element_count": "INTEGER", "windows": "TEXT", "doors": "TEXT",
                                                    "connectors": "INTEGER"})
            self._add_columns("printer_profile", {"clearance_mm": "REAL NOT NULL DEFAULT 0.20"})
            for table, file in _SEEDS.items():
                self._seed(table, _HERE / "seed" / file, replace=table == "scale")
            for scale in SCALES:
                self._insert("rule", seed_rules(scale))

    def _migrate_to_english(self) -> None:
        """Datenbanken bis Oktober 2026 hatten deutsche Tabellen- und Spaltennamen: umbenennen, Daten bleiben."""
        for old_table, (new_table, columns) in _GERMAN_NAMES.items():
            if self._table_exists(old_table) and not self._table_exists(new_table):
                self._conn.execute(f"ALTER TABLE {old_table} RENAME TO {new_table}")
            if not self._table_exists(new_table):
                continue
            existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({new_table})")}
            for old_column, new_column in columns.items():
                if old_column in existing and new_column not in existing:
                    self._conn.execute(f"ALTER TABLE {new_table} RENAME COLUMN {old_column} TO {new_column}")

    def _migrate_rules(self) -> None:
        """Alte Regelsets → Massstab-Schlüssel; CHECK der Aktion um «band» erweitern.

        SQLite kann einen CHECK nicht ändern: Tabelle neu anlegen und Daten übernehmen.
        Benutzerregeln der alten Sets bleiben erhalten, unbekannte Sets werden verworfen.
        """
        sql = self._conn.execute("SELECT sql FROM sqlite_master WHERE name = 'rule'").fetchone()[0]
        if "'band'" not in sql:
            self._conn.execute("ALTER TABLE rule RENAME TO rule_old")
            schema = (_HERE / "schema.sql").read_text(encoding="utf-8")
            start = schema.index("CREATE TABLE IF NOT EXISTS rule (")
            self._conn.execute(schema[start:schema.index(");", start) + 1])
            self._conn.execute("INSERT INTO rule (id, ruleset_name, ifc_class_name, action, category) "
                               "SELECT id, ruleset_name, ifc_class_name, action, category FROM rule_old")
            self._conn.execute("DROP TABLE rule_old")
        for old, new in LEGACY_RULE_SETS.items():
            renamed = self._conn.execute("UPDATE OR IGNORE rule SET ruleset_name = ? WHERE ruleset_name = ?",
                                           (new, old)).rowcount
            if renamed and new == "1:200":     # alter Standardwert, kein Benutzerentscheid: neu als Band
                self._conn.execute("UPDATE rule SET action = 'band' WHERE ruleset_name = '1:200' "
                                   "AND ifc_class_name = 'IfcRailing' AND action = 'entfernen'")
        for key, action in _RETIRED_RULES.items():
            self._conn.execute("DELETE FROM rule WHERE ifc_class_name = ? AND action = ?", (key, action))
        placeholders = ", ".join("?" * len(SCALES))
        discarded = self._conn.execute(f"SELECT DISTINCT ruleset_name FROM rule WHERE ruleset_name NOT IN ({placeholders})",
                                       tuple(SCALES)).fetchall()
        if discarded:
            _LOG.warning("Regelsets ohne Massstab verworfen: %s", ", ".join(z[0] for z in discarded))
            self._conn.execute(f"DELETE FROM rule WHERE ruleset_name NOT IN ({placeholders})", tuple(SCALES))

    def _add_columns(self, table: str, columns: dict[str, str]) -> None:
        """Migration: neue Spalten in einer bestehenden regeln.db nachtragen (CREATE IF NOT EXISTS tut das nicht)."""
        existing = {z["name"] for z in self._conn.execute(f"PRAGMA table_info({table})")}
        for name, predefined_type in columns.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {predefined_type}")

    def _table_exists(self, name: str) -> bool:
        return self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  (name,)).fetchone() is not None

    def _seed(self, table: str, csv_path: Path, replace: bool = False) -> None:
        """CSV einspielen: fehlende Zeilen ergänzen, mit ``replace`` bestehende überschreiben."""
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows = [{k: (None if v == "" else v) for k, v in z.items()} for z in csv.DictReader(f)]
        self._insert(table, rows, replace)

    def _insert(self, table: str, rows: list[dict], replace: bool = False) -> None:
        if rows:
            # Nur _CSV_ONLY wird übergangen: jede andere fehlende Spalte soll beim Start laut scheitern (_add_columns vergessen?)
            columns = [s for s in rows[0] if s not in _CSV_ONLY]
            self._conn.executemany(
                f"INSERT OR {'REPLACE' if replace else 'IGNORE'} INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                [tuple(z[s] for s in columns) for z in rows])

    def _all(self, sql: str, parameter: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(z) for z in self._conn.execute(sql, parameter).fetchall()]

    # --- Regeln -------------------------------------------------------------

    def rule_sets(self) -> list[str]:
        """Die vier Massstab-Stufen in fester Reihenfolge (1:500 … 1:50)."""
        return list(SCALES)

    def scale_parameters(self, ruleset_name: str) -> dict:
        """Parameter eines Massstabs als Zeile (→ core.analysis.ruleset.ScaleParameters.from_row)."""
        rows = self._all("SELECT * FROM scale WHERE ruleset_name = ?", (ruleset_name,))
        if not rows:
            raise ValueError(f"Unbekannter Massstab «{ruleset_name}»")
        return rows[0]

    def reset_rules(self, ruleset_name: str) -> None:
        """Regeln eines Massstabs auf den Standard (Seed) zurücksetzen; eigene Regeln gehen verloren."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM rule WHERE ruleset_name = ?", (ruleset_name,))
            self._insert("rule", seed_rules(ruleset_name))

    def rules(self, ruleset_name: str) -> list[dict]:
        """[{ifc_class_name, action, category}] eines Regelsets."""
        return self._all("SELECT ifc_class_name, action, category FROM rule WHERE ruleset_name = ? "
                          "ORDER BY ifc_class_name", (ruleset_name,))

    def set_action(self, ruleset_name: str, ifc_class_name: str, action: str, category: str = "Sonstiges") -> None:
        """Setzt die Aktion einer Klasse; legt die Regel bei Bedarf an (Kategorie bleibt erhalten)."""
        check_action(action)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO rule (ruleset_name, ifc_class_name, action, category) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ruleset_name, ifc_class_name) DO UPDATE SET action = excluded.action",
                (ruleset_name, ifc_class_name, action, category))

    # --- Stammdaten -----------------------------------------------------------

    def profiles(self) -> list[dict]:
        return self._all("SELECT * FROM printer_profile ORDER BY name")

    def materials(self) -> list[dict]:
        return self._all("SELECT * FROM material ORDER BY name")

    # --- Exportverlauf --------------------------------------------------------

    def write_export_run(self, entry: dict) -> int:
        entry = {"date": datetime.now().isoformat(timespec="seconds"), **entry}
        columns = list(entry)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"INSERT INTO export_run ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                tuple(entry.values()))
            return cur.lastrowid

    def export_runs(self) -> list[dict]:
        return self._all("SELECT * FROM export_run ORDER BY id DESC")

    def close(self) -> None:
        self._conn.close()
