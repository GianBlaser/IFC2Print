"""Oberfläche von IFC2Print (NiceGUI): eine Datei je Blatt, page.py koordiniert.

Zweck:   Alles, was der Nutzer im Browser sieht und bedient. ``page.py`` baut die Seite auf und verbindet die Teile;
         jedes Blatt (``sheet_*.py``), das Panel, die Leisten und der 3D-Viewer (``viewer*.py``) liegen in einer
         eigenen Datei. Die Fachlogik steckt nicht hier, sondern in ``core/``; dazwischen vermittelt der
         Sitzungszustand (``state.py``, ``settings.py``). Das Aussehen steht in ``theme.css``, die Texte in ``texts.py``.
Eingabe: app.py erzeugt je Browser-Tab eine Session und übergibt sie an ``Page``
Ausgabe: die Seite im Browser
"""
