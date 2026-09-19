"""Render the real Qt window at the scale selected with QT_SCALE_FACTOR."""
import os
from pathlib import Path
import tempfile

from PySide6.QtWidgets import QApplication
from tiktok_downloader.app import MainWindow

app = QApplication([])
window = MainWindow(Path(tempfile.mkdtemp()))
output = Path("output") / "screenshots"
output.mkdir(parents=True, exist_ok=True)
window.show()
app.processEvents()
window.grab().save(str(output / "native.png"))
window.close()
