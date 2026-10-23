"""IFC-Schema: Klassenhierarchie nachschlagen (Vererbungskette, alle Produktklassen).

Das Regelwerk sucht über die Vererbungskette des Schemas: IfcSlabStandardCase hat keine eigene Regel und
erbt die von IfcSlab. Die Schemata liefert ifcopenshell; unbekannte Schemata oder Klassen führen nie zu
einem Fehler, sondern zu einer Kette aus nur der Klasse selbst.

Eingabe: Klassenname und Schemakennung (z.B. «IFC4X3_ADD2»)
Ausgabe: Klassennamen als Tupel (``class_chain``: spezifischste zuerst; ``all_classes``: alphabetisch)
"""

from functools import lru_cache

import ifcopenshell.ifcopenshell_wrapper as schema_wrapper


@lru_cache(maxsize=None)
def all_classes(schema: str = "IFC4") -> tuple[str, ...]:
    """Alle Klassen unter IfcProduct im Schema (für die Suche im Regelblatt), alphabetisch."""
    try:
        root_node = schema_wrapper.schema_by_name(schema).declaration_by_name("IfcProduct")
    except (RuntimeError, ValueError, KeyError):
        return ()
    names, is_open = set(), [root_node]
    while is_open:
        d = is_open.pop()
        names.add(d.name())
        is_open += list(d.subtypes())
    return tuple(sorted(names))


@lru_cache(maxsize=None)
def class_chain(ifc_class: str, schema: str | None = None) -> tuple[str, ...]:
    """Die Klasse und ihre Oberklassen, spezifischste zuerst (ohne bekanntes Schema: nur die Klasse).

    ``schema``: Schemakennung der Datei (``ifcopenshell.file.schema_identifier``, z.B. «IFC4X3_ADD2»).
    """
    if not ifc_class or not schema:
        return (ifc_class,) if ifc_class else ()
    try:
        declaration = schema_wrapper.schema_by_name(schema).declaration_by_name(ifc_class)
    except (RuntimeError, ValueError, KeyError):  # unbekanntes Schema oder Klasse (z.B. Tippfehler)
        return (ifc_class,)
    chain = []
    while declaration is not None:
        chain.append(declaration.name())
        declaration = declaration.supertype()
    return tuple(chain)
