"""JavaScript-Bausteine für den 3D-Viewer: Licht und Hintergrund, Bildmitte im freien Bereich, Nachführen der
Gebäudemitte, Kantenlinien, Aufbau-Animation, Abdunkeln, Umriss des gewählten Geschosses und Bauteil-Etikett.

Zweck:   Hier steht JavaScript, weil die NiceGUI-Szene (ui.scene, three.js) diese Dinge nicht selbst anbietet und sie nur
         im Browser direkt am three.js-Objekt einzustellen sind: durchsichtiger Hintergrund mit kräftigerem Licht,
         die Bildmitte in der Mitte des freien Bereichs neben Blatt, Kopfzeile und unterer Leiste, ein weiches Heben
         der Kamera auf die Gebäudemitte, Bauteilkanten als Linien, eine Schnittebene für die Aufbau-Animation, die
         Deckkraft ganzer Geschosse, ein Rahmen um ein Geschoss und ein HTML-Etikett, das einem Punkt im Modell folgt.
         Jeder Baustein ist eine Python-Funktion, die den fertigen JavaScript-Text liefert. In den Vorlagen füllt
         Python die Werte in {id}, {z} usw. ein; ein doppeltes {{ }} ergibt ein einfaches JavaScript-Klammerpaar.
Eingabe: ID der Szene (``scene.id``), je nach Baustein Objekt-IDs, Faktor, Schnitthöhe z, Höhenversatz oder Ankerpunkt
         mit Texten
Ausgabe: JavaScript-Text, den ui/viewer.py mit ``scene.client.run_javascript`` an den Browser schickt
"""

import json

EDGE_ANGLE_DEG = 20      # Grad: flachere Knicke (Rundungen, Triangulierung) bleiben ohne Linie
OUTLINE_COLOR = 0xFF6B2C  # oranger Umriss des gewählten Geschosses
GHOST_MAX_OPACITY = 0.5   # darunter gilt eine Fläche als «nicht gedruckt» (Geist, Deckkraft ≈ 0.18)
CENTER_SMOOTH_MS = 120    # Zeitkonstante, mit der die Bildmitte dem freien Bereich nachgleitet
SHIFT_MS = 400            # Dauer, in der die Kamera auf eine neue Gebäudemitte gleitet

# Einmal nach dem Laden: transparenter Hintergrund (das CSS-Theme scheint durch) und
# kräftigeres Licht. NiceGUI setzt viel Umgebungslicht – das wäscht die Farben aus.
# Bildmitte: setViewOffset verschiebt nur die Projektion, so steht der Blickpunkt (Gebäudemitte) in der Mitte des
# freien Bereichs – rechts vom offenen Blatt (sonst von der Rail), unter der Kopfzeile, über der unteren Leiste.
# Drehpunkt, Klicks und Etikett bleiben dabei stimmig. Neu gemessen wird, wenn Blatt, Kopfzeile oder Viewer die
# Grösse ändern; die Bildmitte gleitet dann weich nach.
_SCENE_SETUP = """
const v = getElement({id});
if (v && v.renderer) {{
  v.renderer.setClearColor(0x000000, 0);
  v.scene.children.forEach((c) => {{
    if (c.isAmbientLight) c.intensity = 1.1;
    if (c.isDirectionalLight) {{ c.intensity = 2.2; c.position.set(-0.6, -0.8, 1.6); }}
  }});
  const app = v.$el.closest(".app");
  if (app && !v.centering) {{
    const c = v.centering = {{ x: 0, y: 0, tx: 0, ty: 0, frame: 0, last: 0 }};
    const rect = (sel) => app.querySelector(sel)?.getBoundingClientRect();
    const step = (now) => {{
      const k = 1 - Math.exp(-(now - c.last) / {smooth_ms});
      c.last = now;
      c.x += (c.tx - c.x) * k;
      c.y += (c.ty - c.y) * k;
      const done = Math.abs(c.tx - c.x) < 0.5 && Math.abs(c.ty - c.y) < 0.5;
      if (done) {{ c.x = c.tx; c.y = c.ty; }}
      const w = v.$el.clientWidth, h = v.$el.clientHeight;
      v.camera.setViewOffset(w, h, -c.x, -c.y, w, h);
      v.camera.updateProjectionMatrix();
      c.frame = done ? 0 : requestAnimationFrame(step);
    }};
    const measure = () => {{
      const own = v.$el.getBoundingClientRect();
      const left = (rect(".sheets .sheet.active") ?? rect(".rail"))?.right ?? own.left;
      const right = rect(".ansicht")?.left ?? own.right;
      const top = rect(".kopf")?.bottom ?? own.top, bottom = rect(".unten-leiste")?.top ?? own.bottom;
      c.tx = (left + right) / 2 - (own.left + own.width / 2);
      c.ty = (top + bottom) / 2 - (own.top + own.height / 2);
      if (!c.frame) {{ c.last = performance.now(); c.frame = requestAnimationFrame(step); }}
    }};
    const observer = new ResizeObserver(measure);
    for (const el of [v.$el, app.querySelector(".sheets"), app.querySelector(".kopf")]) if (el) observer.observe(el);
  }}
}}
"""

# Gebäudemitte in der Höhe nachführen («auseinander», Moduswechsel): Kamera, Drehpunkt und NiceGUIs Blickpunkt
# gleiten gemeinsam um dz – Drehung und Zoom des Nutzers bleiben. Eine neue Verschiebung übernimmt den Rest der
# laufenden; ein Kameraflug von NiceGUI (move_camera) hat Vorrang, er zielt schon auf die richtige Mitte.
_SHIFT_TARGET = """
const v = getElement({id});
if (v && v.controls) {{
  const total = {dz} + (v.shift?.rest ?? 0), start = performance.now(), s = v.shift = {{ rest: total }};
  let moved = 0;
  const step = (now) => {{
    if (v.shift !== s) return;
    if (v.camera_tween?.isPlaying()) {{ v.shift = null; return; }}
    const t = Math.min(1, (now - start) / {ms}), dz = total * t * t * (3 - 2 * t) - moved;
    moved += dz;
    s.rest = total - moved;
    v.camera.position.z += dz;
    v.controls.target.z += dz;
    v.look_at.z += dz;
    if (t < 1) requestAnimationFrame(step); else v.shift = null;
  }};
  requestAnimationFrame(step);
}}
"""

# Aufbau-Animation: globale Clipping-Ebene – alles über der Höhe z wird ausgeblendet
_BUILD_UP = """
const v = getElement({id});
if (v && v.renderer) {{
  const {{ THREE }} = await import("nicegui-scene");
  v.renderer.clippingPlanes = {z} === null ? [] : [new THREE.Plane(new THREE.Vector3(0, 0, -1), {z})];
}}
"""

# Wartet, bis die Objekte im Browser geladen sind, und liefert ihre three.js-Netze (gemeinsamer Anfang der Bausteine)
_MESHES = """
const v = getElement({id});
const meshes = async (ids) => {{
  const found = [];
  for (const oid of ids) {{
    let o;
    for (let n = 0; n < 100 && !(o = v.objects.get(oid)); n++) await new Promise((r) => setTimeout(r, 50));
    if (!o) continue;
    try {{ await o.ready_promise; }} catch {{ continue; }}
    if (o.mesh) found.push(o.mesh);
  }}
  return found;
}};
"""

# IFC-Modus: Bauteilkanten als Linien in derselben Farbe wie die Fläche (Drahtmodell-Look).
# Die Linien hängen als Kind am Netz: NiceGUIs material() färbt sie mit, ihre Deckkraft
# folgt der Fläche aber kräftiger (0.35 + 1.6 × Fläche), damit die Kanten lesbar bleiben.
# Flächen schreiben keine Tiefe mehr, sonst verdecken die durchsichtigen Flächen die Kanten dahinter.
_EDGES = _MESHES + """
if (v && v.objects) {{
  const {{ THREE }} = await import("nicegui-scene");
  for (const root of await meshes({ids})) {{
    const found = [];
    root.traverse((c) => {{ if (c.isMesh && !c.userData.edges) found.push(c); }});
    for (const c of found) {{
      c.userData.edges = true;
      c.material.depthWrite = false;
      const m = new THREE.LineBasicMaterial({{ color: c.material.color.clone(), transparent: true }});
      let alpha = 1;
      Object.defineProperty(m, "opacity", {{ get: () => alpha, set: (w) => {{ alpha = Math.min(1, 0.35 + 1.6 * w); }} }});
      m.opacity = c.material.opacity;
      c.add(new THREE.LineSegments(new THREE.EdgesGeometry(c.geometry, {angle}), m));
    }}
  }}
}}
"""

# STAT/STL: Deckkraft ganzer Geschosse mit einem Faktor (1 = zurück). Die Originaldeckkraft merkt sich jedes Netz
# beim ersten Mal; «nicht gedruckt»-Flächen (Geister) gehen fest auf {ghost}, damit sie nicht ganz verschwinden.
_STOREY_DIM = _MESHES + """
if (v && v.objects) {{
  for (const root of await meshes({ids})) {{
    root.traverse((c) => {{
      if (!c.isMesh || !c.material) return;
      const base = c.userData.baseOpacity ?? (c.userData.baseOpacity = c.material.opacity);
      const dimmed = {factor} < 1;
      c.material.transparent = dimmed || base < 1;
      c.material.opacity = !dimmed ? base : (base < {ghost_max} ? {ghost} : base * {factor});
      c.material.depthWrite = !dimmed && base >= 1;
      c.material.needsUpdate = true;
    }});
  }}
}}
"""

# Oranger Umriss (Box3Helper) um die Objekte des gewählten Geschosses; null entfernt ihn nur.
# Die Laufnummer sorgt dafür, dass nach schnellen Wechseln nur der zuletzt verlangte Umriss bleibt.
_STOREY_OUTLINE = _MESHES + """
if (v && v.scene) {{
  const {{ THREE }} = await import("nicegui-scene");
  const run = v.outlineRun = (v.outlineRun || 0) + 1, ids = {ids}, box = new THREE.Box3();
  if (ids !== null) for (const root of await meshes(ids)) box.expandByObject(root);
  if (run === v.outlineRun) {{
    if (v.storeyOutline) {{ v.scene.remove(v.storeyOutline); v.storeyOutline.geometry.dispose(); v.storeyOutline = null; }}
    if (ids !== null && !box.isEmpty()) {{
      v.storeyOutline = new THREE.Box3Helper(box, {color});
      v.scene.add(v.storeyOutline);
    }}
  }}
}}
"""

# Bauteil-Etikett «Minimal»: Kreis am Anker, daneben Name und Status. Die Position folgt jedem Bild (Kamera bewegt).
_PART_LABEL = """
const v = getElement({id});
if (v && v.camera) {{
  const {{ THREE }} = await import("nicegui-scene");
  if (v.partLabel) {{ cancelAnimationFrame(v.partLabel.frame); v.partLabel.el.remove(); v.partLabel = null; }}
  const anchor = {anchor};
  if (anchor !== null) {{
    const el = document.createElement("div");
    el.className = "etikett";
    el.innerHTML = "<i></i><div><b></b><span></span></div>";
    el.querySelector("b").textContent = {title};
    const status = el.querySelector("span");
    status.textContent = {status};
    status.className = {css_class};
    v.$el.appendChild(el);
    const p = new THREE.Vector3(...anchor), q = new THREE.Vector3(), label = {{ el, frame: 0 }};
    const follow = () => {{
      q.copy(p).project(v.camera);
      const c = v.renderer.domElement;
      el.style.transform = `translate(${{(q.x + 1) / 2 * c.clientWidth}}px, ${{(1 - q.y) / 2 * c.clientHeight}}px)`;
      el.style.display = q.z > 1 ? "none" : "";
      label.frame = requestAnimationFrame(follow);
    }};
    v.partLabel = label;
    follow();
  }}
}}
"""


def scene_setup(scene_id: int) -> str:
    """Hintergrund durchsichtig machen, das Licht kräftiger einstellen und die Bildmitte dem freien Bereich folgen
    lassen."""
    return _SCENE_SETUP.format(id=scene_id, smooth_ms=CENTER_SMOOTH_MS)


def shift_target(scene_id: int, dz: float) -> str:
    """Kamera samt Drehpunkt weich um ``dz`` [mm, Modellmass] heben (negativ = senken)."""
    return _SHIFT_TARGET.format(id=scene_id, dz=f"{dz:.3f}", ms=SHIFT_MS)


def build_up(scene_id: int, z: float | None) -> str:
    """Alles über der Höhe ``z`` [mm, Modellmass] ausblenden; ``None`` = nichts ausblenden."""
    return _BUILD_UP.format(id=scene_id, z="null" if z is None else f"{z:.3f}")


def edges(scene_id: int, object_ids: list[int]) -> str:
    """Kantenlinien an die Netze der Objekte ``object_ids`` hängen (wartet, bis die Objekte im Browser geladen sind)."""
    return _EDGES.format(id=scene_id, ids=json.dumps(object_ids), angle=EDGE_ANGLE_DEG)


def storey_dim(scene_id: int, object_ids: list[int], factor: float, ghost_opacity: float = 0.025) -> str:
    """Deckkraft der Objekte ``object_ids`` × ``factor`` (1 = Original); «nicht gedruckt»-Flächen auf ``ghost_opacity``."""
    return _STOREY_DIM.format(id=scene_id, ids=json.dumps(object_ids), factor=factor, ghost=ghost_opacity,
                              ghost_max=GHOST_MAX_OPACITY)


def storey_outline(scene_id: int, object_ids: list[int] | None) -> str:
    """Orangen Rahmen um die Objekte ``object_ids`` legen (alten ersetzen); ``None`` entfernt ihn."""
    return _STOREY_OUTLINE.format(id=scene_id, ids="null" if object_ids is None else json.dumps(object_ids),
                                  color=OUTLINE_COLOR)


def part_label(scene_id: int, anchor_xyz: tuple[float, float, float] | None, title: str = "", status_text: str = "",
               status_class: str = "") -> str:
    """Etikett am Punkt ``anchor_xyz`` [mm, Modellmass] mit Name und Status (CSS-Klasse der Farbe); None entfernt es."""
    anchor = "null" if anchor_xyz is None else json.dumps([round(float(c), 3) for c in anchor_xyz])
    return _PART_LABEL.format(id=scene_id, anchor=anchor, title=json.dumps(title), status=json.dumps(status_text),
                              css_class=json.dumps(status_class))
