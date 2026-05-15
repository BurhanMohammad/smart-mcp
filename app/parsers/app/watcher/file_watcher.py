from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        print(f"Modified: {event.src_path}")


class FileWatcher:
    def watch(self, path: str):
        observer = Observer()

        observer.schedule(
            ChangeHandler(),
            path,
            recursive=True,
        )

        observer.start()

        try:
            while True:
                pass
        except KeyboardInterrupt:
            observer.stop()

        observer.join()