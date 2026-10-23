"""JavaScript-Bausteine für den 3D-Viewer: Licht und Hintergrund, Kantenlinien, Aufbau-Animation.

Zweck:   Hier steht JavaScript, weil die NiceGUI-Szene (ui.scene, three.js) drei Dinge nicht selbst anbietet und sie nur
         im Browser direkt am three.js-Objekt einzustellen sind: durchsichtiger Hintergrund mit kräftigerem Licht,
         Bauteilkanten als Linien und eine Schnittebene für die Aufbau-Animation. Jeder Baustein ist eine Python-Funktion,
         die den fertigen JavaScript-Text liefert. In den Vorlagen füllt Python die Werte in {id}, {z} usw. ein;
         ein doppeltes {{ }} ergibt ein einfaches JavaScript-Klammerpaar.
Eingabe: ID der Szene (``scene.id``), je nach Baustein Objekt-IDs oder die Schnitthöhe z
Ausgabe: JavaScript-Text, den ui/viewer.py mit ``scene.client.run_javascript`` an den Browser schickt
"""

import json

EDGE_ANGLE_DEG = 20      # Grad: flachere Knicke (Rundungen, Triangulierung) bleiben ohne Linie

# Einmal nach dem Laden: transparenter Hintergrund (das CSS-Theme scheint durch) und
# kräftigeres Licht. NiceGUI setzt viel Umgebungslicht – das wäscht die Farben aus.
_SCENE_SETUP = """
const v = getElement({id});
if (v && v.renderer) {{
  v.renderer.setClearColor(0x000000, 0);
  v.scene.children.forEach((c) => {{
    if (c.isAmbientLight) c.intensity = 1.1;
    if (c.isDirectionalLight) {{ c.intensity = 2.2; c.position.set(-0.6, -0.8, 1.6); }}
  }});
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

# IFC-Modus: Bauteilkanten als Linien in derselben Farbe wie die Fläche (Drahtmodell-Look).
# Die Linien hängen als Kind am Netz: NiceGUIs material() färbt sie mit, ihre Deckkraft
# folgt der Fläche aber kräftiger (0.35 + 1.6 × Fläche), damit die Kanten lesbar bleiben.
# Flächen schreiben keine Tiefe mehr, sonst verdecken die durchsichtigen Flächen die Kanten dahinter.
_EDGES = """
const v = getElement({id});
if (v && v.objects) {{
  const {{ THREE }} = await import("nicegui-scene");
  for (const oid of {ids}) {{
    let o;
    for (let n = 0; n < 100 && !(o = v.objects.get(oid)); n++) await new Promise((r) => setTimeout(r, 50));
    if (!o) continue;
    try {{ await o.ready_promise; }} catch {{ continue; }}
    if (!o.mesh) continue;
    const meshes = [];
    o.mesh.traverse((c) => {{ if (c.isMesh && !c.userData.edges) meshes.push(c); }});
    for (const c of meshes) {{
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


def scene_setup(scene_id: int) -> str:
    """Hintergrund durchsichtig machen und das Licht der Szene kräftiger einstellen."""
    return _SCENE_SETUP.format(id=scene_id)


def build_up(scene_id: int, z: float | None) -> str:
    """Alles über der Höhe ``z`` [mm, Modellmass] ausblenden; ``None`` = nichts ausblenden."""
    return _BUILD_UP.format(id=scene_id, z="null" if z is None else f"{z:.3f}")


def edges(scene_id: int, object_ids: list[int]) -> str:
    """Kantenlinien an die Netze der Objekte ``object_ids`` hängen (wartet, bis die Objekte im Browser geladen sind)."""
    return _EDGES.format(id=scene_id, ids=json.dumps(object_ids), angle=EDGE_ANGLE_DEG)
