"""Blatt 01 «Datei»: IFC-Datei hochladen oder entfernen, Modellkarte des geladenen Modells.

Zweck:   Das Feld zum Ziehen oder Anklicken nimmt eine IFC-Datei an und lässt sie analysieren; darunter zeigt die
         Modellkarte (model_info.py), wie das Modell im Druckbett liegt. «Datei entfernen» bringt die Seite zurück in
         den leeren Startzustand.
Eingabe: die Seite (page) mit Sitzung und Modell-Übersicht; die hochgeladene .ifc-Datei (bis 500 MB)
Ausgabe: das Blatt 01 (Element self.sheet); die geladene Datei steht danach in der Sitzung
"""

from nicegui import events, run, ui

from ui.model_info import ModelInfo
from ui.texts import DROPZONE_SVG, DROPZONE_TEXT
from ui.widgets import button, set_class, sheet_frame, tag

NO_FILE_TEXT = "nur .ifc"
# Beim Darüberziehen einer Datei färbt sich das Feld (Klasse «drag» am Ablagefeld)
_DRAG_ON = "(e) => e.target.closest('.dropzone').classList.add('drag')"
_DRAG_OFF = ("(e) => { const z = e.target.closest('.dropzone'); "
             "if (e.type === 'drop' || !z.contains(e.relatedTarget)) z.classList.remove('drag'); }")


class SheetFile:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        self.model_info = ModelInfo(page)
        with sheet_frame("Datei", "sheet-datei") as self.sheet:
            with ui.element("div").classes("datei-body duenn"):
                with ui.element("div").classes("dropzone") as dropzone:
                    ui.html(DROPZONE_SVG, sanitize=False).classes("dropzone-rahmen")
                    self.upload = ui.upload(auto_upload=True, on_upload=self.uploaded,
                                            max_file_size=500_000_000).props('accept=".ifc" flat').classes("dropzone-upload")
                    self.upload.on("click", lambda: self.upload.run_method("pickFiles"))
                    tag("strong", DROPZONE_TEXT)
                    self.file_label = tag("small", NO_FILE_TEXT)
                dropzone.on("dragenter", js_handler=_DRAG_ON).on("dragover", js_handler=_DRAG_ON)
                dropzone.on("dragleave", js_handler=_DRAG_OFF).on("drop", js_handler=_DRAG_OFF)
                self.model_info.content()
                self.remove_button = button("datei-entfernen hidden", self.remove_file,
                                            text="Datei entfernen").mark("datei-entfernen")

    def set_label(self, text: str) -> None:
        """Zweite Zeile im Ablagefeld: «Beispiel: Datei», der Dateiname oder «nur .ifc»."""
        self.file_label.set_text(text)

    def show_remove_button(self, visible: bool = True) -> None:
        set_class(self.remove_button, "hidden", not visible)

    async def uploaded(self, e: events.UploadEventArguments) -> None:
        """Datei übernehmen, im Hintergrund analysieren und das Modell zeigen."""
        page = self.page
        self.upload.reset()
        self.set_label(e.file.name)
        page.show_message("IFC wird geöffnet und analysiert …")
        try:
            data = await e.file.read()
            await run.io_bound(self.s.load_bytes, data, e.file.name)
        except Exception as error:  # ungültige Datei → verständliche Meldung statt Absturz
            page.show_message(f"Fehler beim Öffnen: {error}", "err")
            self.set_label(self.s.filename or NO_FILE_TEXT)
            return
        if not page.is_alive():   # Seite während der Analyse abgerissen → nichts mehr anfassen
            return
        await page.show_model()
        page.show_message(f"Analyse fertig: {len(self.s.df)} Bauteile.", "ok")

    def remove_file(self) -> None:
        """Leerer Startzustand: Kopfzeile ohne Karten, untere Leiste «Zuerst IFC laden», 05 ohne Zähler."""
        if self.s.running:
            return
        self.s.close_file()
        self.set_label(NO_FILE_TEXT)
        self.show_remove_button(False)
        self.page.clear_analysis()
