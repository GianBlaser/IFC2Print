"""GLB-Zwischenspeicher des Viewers: liefert GLB-Bytes über eine Adresse an den Browser.

Zweck:   ui.scene lädt 3D-Modelle nur über eine URL. Die GLB-Bytes liegen deshalb im Arbeitsspeicher des Servers und
         werden unter /glb/<Schlüssel>.glb ausgeliefert. Jeder Viewer merkt sich seine Schlüssel und gibt sie beim
         Ersetzen und Schliessen wieder frei.
Eingabe: GLB-Bytes (GlbStore.add)
Ausgabe: die Adresse /glb/<Schlüssel>.glb; die Route selbst meldet dieses Modul beim Import an
"""

import uuid

from fastapi import Response
from nicegui import app

GLB_ROUTE = "/glb/{key}.glb"        # Adresse, unter der der Browser die GLB-Dateien holt
# GLB-Bytes je URL-Schlüssel (pro Sitzung; wird beim Ersetzen und Schliessen geleert)
_BLOB_STORE: dict[str, bytes] = {}


@app.get(GLB_ROUTE)
def _glb(key: str) -> Response:
    return Response(_BLOB_STORE.get(key, b""), media_type="model/gltf-binary")


class GlbStore:
    """Die GLB-Dateien eines Viewers; ``release`` räumt sie wieder weg."""

    def __init__(self) -> None:
        self._keys: list[str] = []

    def add(self, data: bytes) -> str:
        """Legt die Bytes ab und liefert die Adresse, unter der der Browser sie holt."""
        key = uuid.uuid4().hex
        _BLOB_STORE[key] = data
        self._keys.append(key)
        return GLB_ROUTE.format(key=key)

    def release(self) -> None:
        for key in self._keys:
            _BLOB_STORE.pop(key, None)
        self._keys.clear()
