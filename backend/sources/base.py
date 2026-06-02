from abc import ABC, abstractmethod

import pandas as pd


class BaseSource(ABC):
    source_name: str

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """Return DataFrame with columns: source, title, content, url, publish_time, fetch_time, extra"""
        ...
