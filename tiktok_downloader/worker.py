"""Isolated worker: uncaught exceptions reach stderr and produce a nonzero exit."""

import json
import sys
import threading

from .core import Control, Downloader, Job


def main():
    job = Job(**json.loads(sys.stdin.readline()))
    control = Control()

    def commands():
        for line in sys.stdin:
            {"pause": control.pause, "resume": control.resume, "stop": control.stop}[line.strip()]()

    threading.Thread(target=commands, daemon=True).start()
    Downloader(job, lambda event: print(json.dumps(event), flush=True), control).run()


if __name__ == "__main__":
    main()
