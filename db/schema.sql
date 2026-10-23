-- IFC2Print – Datenbankschema (SQLite). Angelegt von db.database.Database.

-- Regeln je Massstab (ruleset_name = «1:500» | «1:200» | «1:100» | «1:50», wie config.SCALES).
-- ifc_class_name ist «IfcKlasse», «IfcKlasse.PREDEFINEDTYPE» oder «Ganzes/Teil».
CREATE TABLE IF NOT EXISTS rule (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ruleset_name   TEXT NOT NULL,
    ifc_class_name TEXT NOT NULL,
    action         TEXT NOT NULL CHECK (action IN ('behalten', 'verdicken', 'fuellen', 'band', 'entfernen')),
    category       TEXT NOT NULL,
    UNIQUE (ruleset_name, ifc_class_name)
);

-- Parameter je Massstab (core.analysis.ruleset.ScaleParameters), Modellmass in mm
CREATE TABLE IF NOT EXISTS scale (
    ruleset_name             TEXT PRIMARY KEY,
    denominator              INTEGER NOT NULL UNIQUE,
    min_thickness_wall_mm    REAL NOT NULL,
    min_thickness_railing_mm REAL,            -- NULL = keine Bänder
    reveal_depth_mm          REAL NOT NULL,
    min_core_reveal_mm       REAL NOT NULL,
    qualities                TEXT NOT NULL,   -- «fein,entwurf,auto»
    quality_default          TEXT NOT NULL,
    connectors_allowed       INTEGER NOT NULL,
    window_default           TEXT NOT NULL,
    door_default             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS printer_profile (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    nozzle_mm         REAL NOT NULL,
    layer_height_mm   REAL NOT NULL,
    build_volume_x_mm REAL NOT NULL,
    build_volume_y_mm REAL NOT NULL,
    build_volume_z_mm REAL NOT NULL,
    min_wall_mm       REAL NOT NULL,
    clearance_mm      REAL NOT NULL DEFAULT 0.20   -- Passungsspiel der Steckverbinder
);

CREATE TABLE IF NOT EXISTS material (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    density_g_cm3 REAL NOT NULL,
    price_chf_kg  REAL NOT NULL
);

-- Exportverlauf: ein Eintrag je erzeugtem Modell
CREATE TABLE IF NOT EXISTS export_run (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,                -- ISO-8601
    ifc_name      TEXT NOT NULL,
    scale         INTEGER NOT NULL,
    profile_id    INTEGER REFERENCES printer_profile(id),
    ruleset_name  TEXT NOT NULL,
    mode          TEXT,                         -- Qualität (fein/entwurf)
    window_fill   INTEGER NOT NULL DEFAULT 0,   -- Altlast (früherer Schalter), nicht mehr geschrieben
    part_count    INTEGER,                      -- Geschoss-/Dachteile (bis Okt. 2026: gedruckte Bauteile)
    element_count INTEGER,                      -- gedruckte Bauteile
    windows       TEXT,                         -- Öffnungsmodus Fenster (geschlossen/vertieft/ausgeschnitten)
    doors         TEXT,                         -- Öffnungsmodus Türen
    connectors    INTEGER,                      -- Steckverbinder zwischen den Teilen (0/1)
    filament_g    REAL,
    time_h        REAL,
    cost_chf      REAL
);
