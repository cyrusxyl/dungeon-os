"""One worker thread. Live jobs run before warm jobs."""
import heapq
import itertools
import threading
from typing import Callable

LIVE, WARM = 0, 1


class Job:
    def __init__(self, kind: int, run: Callable[["Job"], None], name: str = ""):
        self.kind = kind
        self.run = run
        self.name = name
        self.cancel = threading.Event()


class Scheduler:
    def __init__(self):
        self._heap: list = []
        self._seq = itertools.count()
        self._cv = threading.Condition()
        self._running: Job | None = None
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tts-worker")
        self._thread.start()

    def submit(self, job: Job) -> Job:
        with self._cv:
            if job.kind == LIVE:
                for _, _, j in self._heap:
                    if j.kind == WARM:
                        j.cancel.set()
                if self._running and self._running.kind == WARM:
                    self._running.cancel.set()
            heapq.heappush(self._heap, (job.kind, next(self._seq), job))
            self._cv.notify()
        return job

    def shutdown(self):
        with self._cv:
            self._stop = True
            self._cv.notify()

    def _loop(self):
        while True:
            with self._cv:
                while not self._heap and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                _, _, job = heapq.heappop(self._heap)
                self._running = job
            try:
                if not job.cancel.is_set():
                    job.run(job)
            except Exception as e:  # keep the worker alive
                print(f"tts job {job.name!r} failed: {e!r}")
            finally:
                with self._cv:
                    self._running = None
