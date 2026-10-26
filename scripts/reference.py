"""Erzeugt docs/REFERENZ.md: alle Stellgrössen und Regeln, so wie sie im Code stehen.

    python scripts/reference.py            # schreibt docs/REFERENZ.md
    python scripts/reference.py --check    # prüft nur (Exit-Code 1, wenn die Datei veraltet ist)

Kein Wert wird von Hand abgeschrieben. Quellen: config.py (Abschnitte «# --- Titel (Modul) ---», Kommentare als
Erklärung), ScaleParameters in core/analysis/ruleset.py und die Seed-CSVs mit ihren Begründungen. Pfade in
Kommentaren («core/voxels/shell.grid_limit») werden zu Links auf die Datei. tests/test_docs.py prüft, dass die
Datei aktuell ist.

Eingabe: Quelltext und db/seed/*.csv des Projekts
Ausgabe: docs/REFERENZ.md (Markdown, Links relativ zu docs/)
"""

import argparse
import ast
import csv
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # Projektordner importierbar

from config import SCALES
from core.analysis.ruleset import DEFAULT_CSV, SCALE_CSV, ScaleParameters, scale_reason

TARGET = ROOT / "docs" / "REFERENZ.md"
SECTION = re.compile(r"^# --- (.+?) -+$")
TITLE_PATH = re.compile(r"^(.+?) \((.+)\)$")                 # «Öffnungen (core/openings/)»
PATH = re.compile(r"\b(?:core|ui|db|scripts|tests)/(?:\w+/)*(?:\w+(?:\.\w+)*)?")
NO_RULE = "–"


# --- Quelltext lesen ------------------------------------------------------------------------------

def _comments(source: str) -> dict[int, tuple[int, str]]:
    """Zeile → (Spalte, Text) jedes Kommentars."""
    return {t.start[0]: (t.start[1], t.string.lstrip("#").strip())
            for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type == tokenize.COMMENT}


def _entries(source: str, nodes: list[ast.stmt]) -> list[tuple]:
    """Abschnitte, Absätze und Konstanten in Reihenfolge des Quelltexts.

    ("section", Titel) | ("text", Absatz) | ("value", Name, Wert, Erklärung). Ein Kommentarblock in der Einrückung der
    Anweisungen wird zum Absatz; Kommentare hinter einer Anweisung und tiefer eingerückte Folgezeilen zur Erklärung.
    Kommentare über anderem Code (Klassen, private Namen) entfallen mit ihm.
    """
    lines = source.splitlines()
    comments = _comments(source)
    starts = {n.lineno: n for n in nodes}
    indent = nodes[0].col_offset if nodes else 0
    entries, block, skip_to = [], [], 0

    def flush():
        if block:
            entries.append(("text", " ".join(block)))
            block.clear()

    for no, line in enumerate(lines, 1):
        if no <= skip_to:
            continue
        stripped = line.strip()
        column = len(line) - len(line.lstrip())
        if no in starts:
            flush()
            node = starts[no]
            notes = [comments[k][1] for k in range(node.lineno, node.end_lineno + 1)
                     if k in comments and not lines[k - 1].strip().startswith("#")]
            skip_to = node.end_lineno
            while skip_to < len(lines) and lines[skip_to].strip().startswith("#") \
                    and comments.get(skip_to + 1, (0, ""))[0] > indent:
                notes.append(comments[skip_to + 1][1])
                skip_to += 1
            name = node.targets[0].id if isinstance(node, ast.Assign) else node.target.id
            value = " ".join(ast.get_source_segment(source, node.value).split())
            entries.append(("value", name, value, " ".join(notes)))
        elif m := SECTION.match(line):
            flush()
            entries.append(("section", m[1]))
        elif stripped.startswith("#") and column == indent:
            block.append(comments[no][1])
        elif not stripped:
            flush()
        else:
            block.clear()
            if entries and entries[-1][0] == "value":
                entries.append(("text", ""))       # anderer Code dazwischen: neue Tabelle
    flush()
    return entries


def _constants(tree: ast.Module) -> list[ast.Assign]:
    """Öffentliche Konstanten (GROSS_GESCHRIEBEN) mit einfachem Wert; Strukturen mit Aufrufen bleiben im Quelltext."""
    return [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper() and not n.targets[0].id.startswith("_")
            and not any(isinstance(x, ast.Call) for x in ast.walk(n.value))]


def _scale_fields() -> tuple[str, dict[str, str]]:
    """Docstring von ScaleParameters und Erklärung je Feld (Kommentar darüber und dahinter)."""
    source = (ROOT / "core" / "analysis" / "ruleset.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "ScaleParameters")
    fields = [n for n in cls.body if isinstance(n, ast.AnnAssign)]
    explanation, pending = {}, []
    for kind, *data in _entries(source, fields):
        if kind == "text":
            pending.append(data[0])
        elif kind == "value":
            explanation[data[0]] = " ".join([*pending, data[2]]).strip()
            pending = []
    return ast.get_docstring(cls) or "", explanation


# --- Markdown -------------------------------------------------------------------------------------

def _target(path: str) -> str | None:
    """Datei oder Ordner eines Pfads aus einem Kommentar: «core/voxels/shell.grid_limit» → core/voxels/shell.py."""
    stem = path.rstrip("/.")
    parts = stem.split(".")
    candidates = [c for i in range(len(parts), 0, -1) for c in (".".join(parts[:i]), ".".join(parts[:i]) + ".py")]
    return next((c for c in candidates if (ROOT / c).exists()), None)


def _link(path: str) -> str:
    """Pfad als Link relativ zu docs/; ein Pfad ohne Datei bleibt als Code stehen (tests/test_docs.py meldet ihn)."""
    target = _target(path)
    return f"[{path}](../{target}{'/' if (ROOT / target).is_dir() else ''})" if target else f"`{path}`"


def _text(text: str, names: set[str]) -> str:
    """Kommentartext für Markdown: Pfade verlinkt, Konstantennamen als Code, «|» maskiert."""
    text = PATH.sub(lambda m: _link(m[0]), text.replace("|", "\\|"))
    return re.sub(r"(?<![`\w])([A-Z][A-Z0-9_]{2,})(?![`\w])", lambda m: f"`{m[1]}`" if m[1] in names else m[1], text)


def _anchor(title: str) -> str:
    """Anker einer Überschrift wie auf GitHub: klein, ohne Satzzeichen, Leerzeichen → «-»."""
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def _number(value) -> str:
    if value is None:
        return NO_RULE
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        return ", ".join(value)
    return str(value)


def _scale_section(names: set[str]) -> list[str]:
    docstring, explanation = _scale_fields()
    parameters = {s: ScaleParameters.default(s) for s in SCALES}
    rows = [f"| `{name}` | " + " | ".join(_number(getattr(p, name)) for p in parameters.values())
            + f" | {_text(explanation.get(name, ''), names)} |"
            for name in explanation if name not in ("ruleset_name", "denominator")]
    return ["## Parameter je Massstab", "",
            f"Code: {_link('core/analysis/ruleset.py')} (`ScaleParameters`) · Werte und Begründungen: "
            f"{_link('db/seed/massstaebe.csv')}", "",
            _text(" ".join(docstring.split()), names), "",
            "| Parameter | " + " | ".join(SCALES) + " | Erklärung |", "|---|" + "---|" * len(SCALES) + "---|",
            *rows, "", *[f"- **{s}:** {_text(scale_reason(s), names)}" for s in SCALES], ""]


def _rule_section(names: set[str]) -> list[str]:
    with DEFAULT_CSV.open(encoding="utf-8", newline="") as f:
        seed = list(csv.DictReader(f))
    rules: dict[str, dict[str, dict]] = {}
    for row in seed:
        rules.setdefault(row["ifc_class_name"], {})[row["ruleset_name"]] = row
    lines = ["## Klassenregeln", "",
             f"Code: {_link('core/analysis/ruleset.py')} (`Ruleset`) · Werte und Begründungen: {_link('db/seed/regeln.csv')}"
             f" · Aktionen, Vererbung und Aggregate: [README › Regeln](../README.md#regeln)", "",
             f"Standard je Massstab; eigene Regeln speichert die Datenbank. {NO_RULE} = keine eigene Regel, es gilt die "
             "Regel der Oberklasse.", "",
             "| Regel | Kategorie | " + " | ".join(SCALES) + " | Begründung |", "|---|---|" + "---|" * len(SCALES) + "---|"]
    for key, by_scale in rules.items():
        reasons: dict[str, list[str]] = {}
        for scale, row in by_scale.items():
            reasons.setdefault(row["reason"], []).append(scale)
        reason = next(iter(reasons)) if len(reasons) == 1 else "<br>".join(
            f"**{', '.join(scales)}:** {text}" for text, scales in reasons.items())
        category = next(iter(by_scale.values()))["category"]
        actions = " | ".join(by_scale[s]["action"] if s in by_scale else NO_RULE for s in SCALES)
        lines.append(f"| `{key}` | {category} | {actions} | {_text(reason, names)} |")
    return lines + [""]


def _chunks(entries: list[tuple]) -> list[tuple]:
    """Absatz mit den Konstanten darunter zusammenfassen: ("section", Titel) | ("values", Absatz, [(Name, Wert, Erklärung)])."""
    chunks = []
    for kind, *data in entries:
        if kind == "section":
            chunks.append(("section", data[0]))
        elif kind == "text" or not chunks or chunks[-1][0] == "section":
            chunks.append(("values", data[0] if kind == "text" else "", []))
        if kind == "value":
            chunks[-1][2].append(tuple(data))
    return chunks


def _config_sections(source: str, names: set[str]) -> tuple[list[str], list[str]]:
    """Abschnitte von config.py: (Markdown-Zeilen, Titel für das Inhaltsverzeichnis).

    Ein Absatz wird zur Erklärung der ersten Konstante darunter, wenn nur ihr eine eigene Erklärung fehlt; sonst
    gilt er für mehrere und steht vor der Tabelle.
    """
    lines, titles, in_table = [], [], False
    for chunk in _chunks(_entries(source, _constants(ast.parse(source)))):
        if chunk[0] == "section":
            m = TITLE_PATH.match(chunk[1])
            title, path = (m[1], m[2]) if m else (chunk[1], "")
            titles.append(title)
            lines += ["", f"## {title}", ""] + ([f"Code: {_link(path)}", ""] if path else [])
            in_table = False
            continue
        _, text, values = chunk
        if text and values and not values[0][2] and all(note for *_, note in values[1:]):
            values = [(values[0][0], values[0][1], text), *values[1:]]
        else:
            if text or not values:
                lines += ["", _text(text, names), ""]
            in_table = False
        for name, value, note in values:
            if not in_table:
                lines += ["", "| Konstante | Wert | Erklärung |", "|---|---|---|"]
                in_table = True
            value = value.replace("|", "\\|")
            lines.append(f"| `{name}` | `{value}` | {_text(note, names)} |")
    return lines, titles


def render() -> str:
    """Inhalt von docs/REFERENZ.md."""
    source = (ROOT / "config.py").read_text(encoding="utf-8")
    names = {n.targets[0].id for n in _constants(ast.parse(source))}
    config_lines, titles = _config_sections(source, names)
    lines = ["# Referenz – Stellgrössen und Regeln", "",
             "Automatisch erzeugt mit `python scripts/reference.py` aus [config.py](../config.py), "
             f"{_link('core/analysis/ruleset.py')} und {_link('db/seed/')}. Nicht von Hand ändern: "
             "`tests/test_docs.py` schlägt fehl, sobald die Datei nicht mehr zum Code passt. Was die Verfahren tun, "
             "erklärt das [README](../README.md); hier steht, mit welchen Werten und warum.", "",
             "## Inhalt", "", *[f"- [{t}](#{_anchor(t)})" for t in ["Parameter je Massstab", "Klassenregeln", *titles]], "",
             *_scale_section(names), *_rule_section(names), *config_lines]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="nur prüfen, ob docs/REFERENZ.md aktuell ist")
    args = parser.parse_args()
    text = render()
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    if args.check:
        print("aktuell" if current == text else "veraltet: python scripts/reference.py ausführen")
        return 0 if current == text else 1
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"{TARGET.relative_to(ROOT)} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
