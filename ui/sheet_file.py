"""Blatt 01 «Datei»: IFC-Datei hochladen oder wieder entfernen.

Zweck:   Das Feld zum Ziehen oder Anklicken nimmt eine IFC-Datei an und lässt sie analysieren; «Datei entfernen»
         bringt die Seite zurück in den leeren Startzustand.
Eingabe: die Seite (page) mit Sitzung; die hochgeladene .ifc-Datei (bis 500 MB)
Ausgabe: das Blatt 01 (Element self.sheet); die geladene Datei steht danach in der Sitzung
"""

from nicegui import events, run, ui

from ui.texts import DROPZONE_TEXT
from ui.widgets import button, set_class, sheet_frame, tag


class SheetFile:
    def __init__(self, page):
        self.page = page
        self.s = page.s
        with sheet_frame("Datei", "01 / 05") as self.sheet:
            with ui.element("div").classes("sheet-body"):
                with ui.element("div").classes("dropzone"):
                    self.upload = ui.upload(auto_upload=True, on_upload=self.uploaded,
                                            max_file_size=500_000_000).props('accept=".ifc" flat').classes("dropzone-upload")
                    self.upload.on("click", lambda: self.upload.run_method("pickFiles"))
                    self.file_label = tag("strong", DROPZONE_TEXT)
                    tag("span", "nur .ifc", "hint")
                self.remove_button = button("btn btn-ghost btn-pill hidden", self.remove_file,
                                            text="Datei entfernen").mark("datei-entfernen")

    def set_label(self, text: str) -> None:
        """Text im Ziehfeld (Dateiname oder Aufforderung)."""
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
            return
        if not page.is_alive():   # Seite während der Analyse abgerissen → nichts mehr anfassen
            return
        await page.show_model()
        page.show_message(f"Analyse fertig: {len(self.s.df)} Bauteile.", "ok")

    def remove_file(self) -> None:
        """Leerer Startzustand: Panel und untere Leiste zeigen «Zuerst IFC laden», 05 ohne Zähler."""
        if self.s.running:
            return
        self.s.close_file()
        self.set_label(DROPZONE_TEXT)
        self.show_remove_button(False)
        self.page.clear_analysis()
