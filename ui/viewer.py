"""3D-Viewer: ui.scene (three.js ist in NiceGUI eingebaut) mit GLB-Dateien je Geschoss.

Zweck:   Zeigt die Geometrie, die fertig aus core.output.preview kommt (samt Farben). Hier wird nur angezeigt:
         Modus (IFC / Status / STL), Geschosse auseinander, Geschoss-Fokus, Aufbau-Animation beim Erzeugen und die
         Kamera. Das Druckbett zeichnet ui/viewer_bed.py, die GLB-Dateien liefert ui/viewer_blobs.py aus und die
         kleinen JavaScript-Ergänzungen stehen in ui/viewer_js.py.
Eingabe: GLB-Bytes je Geschoss (Session.preview, Session.selection_preview), Kameramasse (Session.frame), Theme;
         optional ein Klick-Callback ``on_pick``
Ausgabe: die Szene im Browser (Klasse Viewer); Klicks ins Modell gehen als Treffer an ``on_pick``
"""

from nicegui import ui

from ui import viewer_js
from ui.viewer_bed import PrintBed
from ui.viewer_blobs import GlbStore

# «Geschosse auseinander»: Abstand je Geschoss als Anteil der mittleren Geschosshöhe
EXPLODE_FACTOR = 1.0
# Deckkraft im IFC-Modus: alle gleich, gewähltes Geschoss, abgedimmte Geschosse
OPACITY_IFC, OPACITY_FOCUS, OPACITY_DIMMED = 0.05, 0.22, 0.015


class Viewer:
    """Vollflächiger Viewer im Hintergrund."""

    def __init__(self, on_pick=None):
        """``on_pick(hits, multi_select)``: ``hits`` = [(Geschoss, (x, y, z))] von nah nach fern, Modellmass."""
        self.on_pick = on_pick
        self.scene = ui.scene(grid=False, background_color="#000000", on_click=self._click,
                              click_events=["click"]).classes("viewer")
        self.bed = PrintBed(self.scene)
        self._blobs = GlbStore()
        self.mode = "ifc"
        self.exploded = False
        self._scene_layers: dict[str, list] = {"ifc": [], "status": [], "stl": [], "selection": []}   # [(Objekt, Rang)]
        self._object_storey: dict[str, tuple[str, int]] = {}   # Objekt-ID → (Geschoss, Rang) für Klicks
        self._rank: dict[str, int] = {}                          # Geschoss → Rang (von unten)
        self._name: dict[int, str] = {}                  # id(Objekt) → Geschoss/Teil (zum Ausblenden)
        self.hidden: set[str] = set()                 # ausgeblendete Geschosse
        self.only_selection = False                   # nur die Ebene «selection» zeigen (Klick in der Matrix)
        self._ifc_color: dict[int, tuple[str, str]] = {}   # id(Objekt) → (Geschoss, Farbe) der IFC-Objekte
        self._focus: str | None = None
        self._z_bottom = 0.0
        self._height = 0.0
        ui.timer(0.5, lambda: self.scene.client.run_javascript(viewer_js.scene_setup(self.scene.id)), once=True)

    # --- Inhalte ----------------------------------------------------------

    def _add_glb(self, layer: str, data: bytes, name: str, rank: int, pickable: bool = False):
        """Lädt ein GLB in die Szene (nur innerhalb von ``with self.scene``) und trägt es in die Ebene ein.

        ``name`` ist das Geschoss bzw. der Teilname (zum Ausblenden); ``pickable``: ein Klick trifft das Objekt.
        """
        obj = self.scene.gltf(self._blobs.add(data))
        self._name[id(obj)] = name
        self._scene_layers[layer].append((obj, rank))
        if pickable:
            self._object_storey[obj.id] = (name, rank)
        return obj

    def _clear(self, *modes: str) -> None:
        for m in modes:
            for obj, _ in self._scene_layers[m]:
                self._name.pop(id(obj), None)
                obj.delete()
            self._scene_layers[m] = []

    def building_elements(self, ifc_glb: dict[str, tuple[bytes | None, bytes | None]], status_glb: dict[str, bytes],
                 colors: dict[str, str]) -> None:
        """Lädt die Bauteile je Geschoss: IFC-Modus (Geschossfarbe + rote Defekte) und Status-Modus."""
        self.release()
        self._clear("ifc", "status", "stl", "selection")
        self.only_selection = False                   # die Auswahl-Ebene ist weg, sonst bliebe alles unsichtbar
        self._ifc_color.clear()
        self._object_storey.clear()
        self._rank = {g: rank for rank, g in enumerate(ifc_glb)}
        with self.scene:
            for rank, (storey, (normal, defective)) in enumerate(ifc_glb.items()):
                if normal:
                    obj = self._add_glb("ifc", normal, storey, rank, pickable=True)
                    self._ifc_color[id(obj)] = (storey, colors.get(storey, "#5AA9FF"))
                if defective:
                    self._add_glb("ifc", defective, storey, rank, pickable=True)
            for rank, (storey, data) in enumerate(status_glb.items()):
                self._add_glb("status", data, storey, rank, pickable=True)
        self._focus = None
        self._apply()
        ifc_ids = [obj.id for obj, _ in self._scene_layers["ifc"]]
        if ifc_ids:
            self.scene.client.run_javascript(viewer_js.edges(self.scene.id, ifc_ids))

    def highlight(self, glb_per_storey: dict[str, bytes]) -> None:
        """Zeigt die gewählten Bauteile (ein GLB je Geschoss) über dem Modell; leer = nichts hervorheben."""
        self._clear("selection")
        with self.scene:
            for storey, data in glb_per_storey.items():
                self._add_glb("selection", data, storey, self._rank.get(storey, 0))
        self._apply()

    def stl(self, pieces_glb: dict[str, bytes]) -> None:
        """Lädt die erzeugten Geschoss-Teile für den STL-Modus."""
        self._clear("stl")
        with self.scene:
            for rank, (name, data) in enumerate(pieces_glb.items()):
                self._add_glb("stl", data, name, rank)
        self._apply()

    def release(self) -> None:
        """GLB-Dateien dieses Viewers aus dem Zwischenspeicher entfernen (beim Ersetzen und Schliessen)."""
        self._blobs.release()

    async def _click(self, e) -> None:
        """Scene-Klick → Treffer je Geschoss (ohne den «auseinander»-Versatz)."""
        if self.on_pick is None or self.mode == "stl":
            return
        step = self._step("status")
        hits = []
        for h in e.hits:
            if h.object_id in self._object_storey:
                storey, rank = self._object_storey[h.object_id]
                hits.append((storey, (h.x, h.y, h.z - rank * step)))
        if hits:
            await self.on_pick(hits, bool(e.ctrl or e.meta or e.shift))

    # --- Darstellung ------------------------------------------------------

    def _step(self, mode: str) -> float:
        """«auseinander»: jedes Geschoss rückt um eine mittlere Geschosshöhe vom darunterliegenden ab."""
        count = len(self._scene_layers["stl"]) if mode == "stl" else len(self._rank)   # IFC/Status/Auswahl: je Geschoss
        return EXPLODE_FACTOR * self._height / max(1, count) if self.exploded else 0.0

    def _apply(self) -> None:
        stl_present = bool(self._scene_layers["stl"])
        visible = "stl" if self.mode == "stl" and stl_present else ("status" if self.mode == "stl" else self.mode)
        for mode, plane in self._scene_layers.items():
            step = self._step(mode)
            for obj, rank in plane:
                enabled = (visible in ("ifc", "status") if mode == "selection"
                           else mode == visible and not (self.only_selection and mode != "stl"))
                obj.visible(enabled and self._name.get(id(obj)) not in self.hidden)
                obj.move(0, 0, rank * step)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._apply()

    def set_exploded(self, enabled: bool) -> None:
        self.exploded = enabled
        self._apply()

    def focus(self, storey: str | None) -> None:
        """Hebt ein Geschoss im IFC-Modus hervor und dimmt die anderen (None = alle gleich)."""
        self._focus = storey
        for obj, _ in self._scene_layers["ifc"]:
            if id(obj) in self._ifc_color:
                name, color = self._ifc_color[id(obj)]
                opacity = OPACITY_IFC if storey is None else (OPACITY_FOCUS if name == storey else OPACITY_DIMMED)
                obj.material(color, opacity)

    def hide(self, hidden: set[str]) -> None:
        """Geschosse (bzw. gleichnamige STL-Teile) aus- und wieder einblenden."""
        self.hidden = set(hidden)
        self._apply()

    def isolate(self, enabled: bool) -> None:
        """Nur die hervorgehobenen Bauteile zeigen (IFC- und Status-Ebene aus) bzw. wieder alles."""
        self.only_selection = enabled
        self._apply()

    def build_up(self, fraction: float | None) -> None:
        """Aufbau-Animation: zeigt das Modell nur bis zum Anteil ``fraction`` seiner Höhe (None = ganz)."""
        # +0.05 mm: das Gitter auf Bodenhöhe bleibt auch bei 0 % sichtbar
        z = None if fraction is None else self._z_bottom + 0.05 + max(0.0, min(1.0, fraction)) * self._height
        self.scene.client.run_javascript(viewer_js.build_up(self.scene.id, z))

    def theme(self, theme: str) -> None:
        self.bed.set_theme(theme)

    # --- Kamera -------------------------------------------------------------

    def frame(self, center, size: float, height: float, print_bed_mm: tuple[float, float], theme: str) -> None:
        """Kamera auf das Modell richten, Druckbett-Gitter mit Bauraumrahmen darunter legen."""
        self._height = height
        x, y, z = (float(v) for v in center)
        self._z_bottom = z
        self.bed.draw(x, y, z, print_bed_mm)
        self.theme(theme)
        d = max(size, 30) * 1.15
        # Blickpunkt leicht nach links versetzt: das Modell steht rechts neben den Blättern
        self.scene.move_camera(x=x + d * 0.55, y=y - d * 0.95, z=z + d * 0.7,
                               look_at_x=x - size * 0.22, look_at_y=y, look_at_z=z + height * 0.4, duration=0.8)

    def display(self, lo, hi) -> None:
        """Kamera auf ein Bauteil richten (Box im Modellmass, ohne «auseinander»-Versatz)."""
        center = [(float(a) + float(b)) / 2 for a, b in zip(lo, hi)]
        d = max(max(float(b) - float(a) for a, b in zip(lo, hi)), 8.0) * 3.0
        self.scene.move_camera(x=center[0] + d * 0.6, y=center[1] - d, z=center[2] + d * 0.7,
                               look_at_x=center[0], look_at_y=center[1], look_at_z=center[2], duration=0.6)
