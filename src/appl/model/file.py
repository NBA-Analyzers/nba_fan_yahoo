from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FilePurpose(Enum):
    GENERAL = "general"
    LEAGUE = "league"


@dataclass
class FileMetadata:
    file_id: str
    file_name: str
    openai_file_id: str
    league_id: Optional[str]
    file_path_s3: str


@dataclass
class UpdateFile:
    file_name: str
    file_path: str


@dataclass
class OpenaiStoredFiles:
    openai_vs_id: str
    file_metadata: list[FileMetadata]
