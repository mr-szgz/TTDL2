"""Launch the real GUI and browser for review; indexing remains manual."""
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from tiktok_downloader.app import MainWindow

app = QApplication(sys.argv)
app.setOrganizationName("TikTokDownloader2")
app.setApplicationName("TikTok Downloader 2")
window = MainWindow()
window.settings.browser = "chromium"
window.settings.executable = ""
window.source.setText("https://www.tiktok.com/@sydneysweeneyfann")
window.show()
output = Path(__file__).resolve().parents[1] / "output"
output.mkdir(exist_ok=True)

def snapshot():
    (output / "live-review-status.txt").write_text(
        window.statusBar().currentMessage() + "\n" + window.log.toPlainText(), encoding="utf-8")
    window.grab().save(str(output / "live-review.png"))

timer = QTimer()
timer.timeout.connect(snapshot)
timer.start(1000)
QTimer.singleShot(500, window.download.click)
sys.exit(app.exec())
