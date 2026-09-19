"""Isolated worker: uncaught exceptions reach stderr and produce a nonzero exit."""

import json
import sys
import threading

from .core import Control, Downloader, Job


def main():
    request = json.loads(sys.stdin.readline())
    job = Job(**request["job"])
    control = Control()

    def commands():
        for line in sys.stdin:
            {"pause": control.pause, "resume": control.resume, "stop": control.stop}[line.strip()]()

    threading.Thread(target=commands, daemon=True).start()
    downloader = Downloader(job, lambda event: print(json.dumps(event), flush=True), control)
    if request["links"] is None:
        downloader.scan()
    else:
        downloader.run(request["links"])


if __name__ == "__main__":
    main()
