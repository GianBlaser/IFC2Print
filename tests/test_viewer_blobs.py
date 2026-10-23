"""Test des GLB-Zwischenspeichers: die Route /glb/<Schlüssel>.glb liefert die abgelegten Bytes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ui import viewer_blobs
from ui.viewer_blobs import GlbStore


def test_glb_route_delivers_stored_bytes():
    """Der Browser holt die GLB-Datei über die Adresse aus GlbStore.add; nach release() ist sie weg.

    Die Route kommt in eine eigene kleine App: Die Testumgebung von NiceGUI setzt die Routen der echten App zurück.
    """
    api = FastAPI()
    api.get(viewer_blobs.GLB_ROUTE)(viewer_blobs._glb)
    client = TestClient(api)
    store = GlbStore()
    url = store.add(b"glTF-test")
    response = client.get(url)
    assert response.status_code == 200 and response.content == b"glTF-test"
    store.release()
    assert client.get(url).content == b""
