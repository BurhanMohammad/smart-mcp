from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        print(f'Updated: {event.src_path}')


class RepositoryWatcher:
    def __init__(self, path):
        self.path = path

    def start(self):
        observer = Observer()

        observer.schedule(
            ChangeHandler(),
            self.path,
            recursive=True
        )

        observer.start()

        print('Watch mode enabled')
