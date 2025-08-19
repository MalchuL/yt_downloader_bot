from typing import List, Optional
from pathlib import Path
from abc import ABC, abstractmethod

class Splitter(ABC):
    """
    Splitter is a class that splits a video into smaller parts.
    """
    @abstractmethod
    def split_by_size(self, input_path: str | Path, 
                      output_dir: str | Path,
                      size_mb: int = 100) -> List[Path]:
        """
        Split the video into smaller parts by size.
        """
