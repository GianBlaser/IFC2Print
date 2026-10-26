"""3D-Viewer: ui.scene (three.js ist in NiceGUI eingebaut) mit GLB-Dateien je Geschoss.

Zweck:   Zeigt die Geometrie, die fertig aus core.output.preview kommt (samt Farben). Hier wird nur angezeigt:
         Modus (IFC / Status / STL), Geschosse auseinander, Geschoss-Fokus und gewähltes Geschoss (andere abgedunkelt,
         oranger Umriss), Etikett am gewählten Bauteil, Aufbau-Animation beim Erzeugen und die Kamera (Blickpunkt auf
         der Gebäudemitte samt «auseinander», im Bild mittig im freien Bereich neben den Blättern). Das Druckbett
         zeichnet ui/viewer_bed.py, die GLB-Dateien liefert ui/viewer_blobs.py aus und die kleinen JavaScript-Ergänzungen
         stehen in ui/viewer_js.py.
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
# STAT/STL mit gewähltem Geschoss: andere Geschosse × Faktor, ihre «nicht gedruckt»-Flächen auf feste Deckkraft
DIM_FACTOR, DIM_GHOST_OPACITY = 0.10, 0.025


def belongs_to(name: str, storey: str) -> bool:
    """Gehört das Objekt (Geschoss bzw. STL-Teil) zum Geschoss? Die eigene Decke ist ein Teil «Decke <Geschoss>»."""
    return name in (storey, f"Decke {storey}")


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
        self._name: dict[int, str] = {}                  # id(Objekt) → Geschoss/Teil
        self._ifc_color: dict[int, tuple[str, str]] = {}   # id(Objekt) → (Geschoss, Farbe) der IFC-Objekte
        self._focus: str | None = None                 # Geschoss unter der Maus (Matrix-Karte)
        self.selected_storey: str | None = None        # in der Matrix gewähltes Geschoss
        self._label: tuple | None = None               # (Box, Geschoss, Name, Status, CSS-Klasse) des Etiketts
        self._dimmed = self._outlined = False          # im Browser abgedunkelt bzw. Umriss vorhanden
        self._z_bottom = 0.0
        self._height = 0.0
        self._shown_center_z: float | None = None        # Höhe des Blickpunkts im Browser (None = noch kein frame)
        ui.timer(0.5, lambda: self.scene.client.run_javascript(viewer_js.scene_setup(self.scene.id)), once=True)

    # --- Inhalte ----------------------------------------------------------

    def _add_glb(self, layer: str, data: bytes, name: str, rank: int, pickable: bool = False):
        """Lädt ein GLB in die Szene (nur innerhalb von ``with self.scene``) und trägt es in die Ebene ein.

        ``name`` ist das Geschoss bzw. der Teilname; ``pickable``: ein Klick trifft das Objekt.
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
        self._dimmed = False                           # alles neu geladen, also voll sichtbar
        if self.selected_storey not in self._rank:
            self.selected_storey = None
        self._apply()
        ifc_ids = [obj.id for obj, _ in self._scene_layers["ifc"]]
        if ifc_ids:
            self.scene.client.run_javascript(viewer_js.edges(self.scene.id, ifc_ids))
        self.select_storey(self.selected_storey)

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
        self._dim()
        self._outline()

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

    def _visible_layer(self) -> str:
        """Ebene, die der Modus zeigt: STL ohne erzeugte Teile zeigt die Druckbarkeit (Status)."""
        if self.mode == "stl":
            return "stl" if self._scene_layers["stl"] else "status"
        return self.mode

    @property
    def shows_status(self) -> bool:
        """True, wenn der Viewer gerade die Druckbarkeit zeigt (STAT, oder STL ohne Ergebnis)."""
        return self._visible_layer() == "status"

    def _apply(self) -> None:
        visible = self._visible_layer()
        for mode, plane in self._scene_layers.items():
            step = self._step(mode)
            for obj, rank in plane:
                obj.visible(visible in ("ifc", "status") if mode == "selection" else mode == visible)
                obj.move(0, 0, rank * step)
        self._recenter()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._apply()
        self._outline()

    def set_exploded(self, enabled: bool) -> None:
        self.exploded = enabled
        self._apply()
        self._outline()
        self._show_label()

    def focus(self, storey: str | None) -> None:
        """Hebt ein Geschoss im IFC-Modus hervor und dimmt die anderen (None = zurück zur Auswahl der Matrix).

        Die Maus über einer Karte hat Vorrang; ohne sie gilt das gewählte Geschoss, ohne Auswahl sind alle gleich."""
        self._focus = storey
        shown = storey if storey is not None else self.selected_storey
        for obj, _ in self._scene_layers["ifc"]:
            if id(obj) in self._ifc_color:
                name, color = self._ifc_color[id(obj)]
                opacity = OPACITY_IFC if shown is None else (OPACITY_FOCUS if name == shown else OPACITY_DIMMED)
                obj.material(color, opacity)

    def select_storey(self, storey: str | None) -> None:
        """Geschoss aus der Matrix wählen: IFC wie der Fokus, STAT/STL andere Geschosse stark durchsichtig,
        oranger Umriss um das gewählte (None = alles wieder voll)."""
        self.selected_storey = storey
        self.focus(self._focus)
        self._dim()
        self._outline()

    def _dim(self) -> None:
        """STAT und STL: andere Geschosse (bzw. STL-Teile) × DIM_FACTOR, das gewählte voll."""
        storey = self.selected_storey
        if storey is None and not self._dimmed:
            return
        self._dimmed = storey is not None
        objects = [(obj, self._name.get(id(obj), "")) for layer in ("status", "stl") for obj, _ in self._scene_layers[layer]]
        own = [obj.id for obj, name in objects if storey is None or belongs_to(name, storey)]
        others = [obj.id for obj, name in objects if storey is not None and not belongs_to(name, storey)]
        run = self.scene.client.run_javascript
        if own:
            run(viewer_js.storey_dim(self.scene.id, own, 1))
        if others:
            run(viewer_js.storey_dim(self.scene.id, others, DIM_FACTOR, DIM_GHOST_OPACITY))

    def _outline(self) -> None:
        """Umriss um das gewählte Geschoss in der sichtbaren Ebene (nach Moduswechsel und «auseinander» neu)."""
        storey = self.selected_storey
        if storey is None and not self._outlined:
            return
        self._outlined = storey is not None
        ids = None if storey is None else [obj.id for obj, _ in self._scene_layers[self._visible_layer()]
                                           if belongs_to(self._name.get(id(obj), ""), storey)]
        self.scene.client.run_javascript(viewer_js.storey_outline(self.scene.id, ids or None))

    def label(self, box: tuple | None, storey: str = "", title: str = "", status_text: str = "",
              status_class: str = "") -> None:
        """Etikett «Name + Status» an der Mitte der Box (Modellmass) eines Bauteils; ``box`` None entfernt es."""
        self._label = None if box is None else (box, storey, title, status_text, status_class)
        self._show_label()

    def _show_label(self) -> None:
        if self._label is None:
            self.scene.client.run_javascript(viewer_js.part_label(self.scene.id, None))
            return
        (lo, hi), storey, title, status_text, status_class = self._label
        center = [(float(a) + float(b)) / 2 for a, b in zip(lo, hi)]
        center[2] += self._rank.get(storey, 0) * self._step("status")      # Versatz «auseinander»
        self.scene.client.run_javascript(viewer_js.part_label(self.scene.id, center, title, status_text, status_class))

    def build_up(self, fraction: float | None) -> None:
        """Aufbau-Animation: zeigt das Modell nur bis zum Anteil ``fraction`` seiner Höhe (None = ganz)."""
        # +0.05 mm: das Gitter auf Bodenhöhe bleibt auch bei 0 % sichtbar
        z = None if fraction is None else self._z_bottom + 0.05 + max(0.0, min(1.0, fraction)) * self._height
        self.scene.client.run_javascript(viewer_js.build_up(self.scene.id, z))

    def theme(self, theme: str) -> None:
        self.bed.set_theme(theme)

    # --- Kamera -------------------------------------------------------------
    # Seitlich verschiebt nichts mehr: viewer_js.scene_setup legt die Bildmitte in den freien Bereich neben den Blättern.

    def _center_z(self) -> float:
        """Höhe der Gebäudemitte in der sichtbaren Ebene, samt «auseinander»-Versatz des obersten Geschosses (Teils)."""
        layer = self._visible_layer()
        top_rank = max((rank for _, rank in self._scene_layers[layer]), default=0)
        return self._z_bottom + (self._height + top_rank * self._step(layer)) / 2

    def _recenter(self) -> None:
        """Kamera samt Drehpunkt weich auf die neue Gebäudemitte heben bzw. senken (Drehung und Zoom bleiben)."""
        if self._shown_center_z is None:
            return
        z = self._center_z()
        if abs(z - self._shown_center_z) > 0.01:
            self.scene.client.run_javascript(viewer_js.shift_target(self.scene.id, z - self._shown_center_z))
            self._shown_center_z = z

    def frame(self, center, size: float, height: float, print_bed_mm: tuple[float, float], theme: str) -> None:
        """Kamera auf das Modell richten, Druckbett-Gitter mit Bauraumrahmen darunter legen."""
        self._height = height
        x, y, z = (float(v) for v in center)
        self._z_bottom = z
        self.bed.draw(x, y, z, print_bed_mm)
        self.theme(theme)
        d = max(size, 30) * 1.15
        zc = self._shown_center_z = self._center_z()
        self.scene.move_camera(x=x + d * 0.55, y=y - d * 0.95, z=zc + d * 0.7,
                               look_at_x=x, look_at_y=y, look_at_z=zc, duration=0.8)

    def display(self, lo, hi, storey: str = "") -> None:
        """Kamera auf ein Bauteil richten (Box im Modellmass, ohne «auseinander»-Versatz; ``storey`` rechnet ihn ein)."""
        center = [(float(a) + float(b)) / 2 for a, b in zip(lo, hi)]
        center[2] += self._rank.get(storey, 0) * self._step("status")
        d = max(max(float(b) - float(a) for a, b in zip(lo, hi)), 8.0) * 3.0
        self.scene.move_camera(x=center[0] + d * 0.6, y=center[1] - d, z=center[2] + d * 0.7,
                               look_at_x=center[0], look_at_y=center[1], look_at_z=center[2], duration=0.6)
