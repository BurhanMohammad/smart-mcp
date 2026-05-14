from abc import ABC
from abc import abstractmethod


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str):
        pass