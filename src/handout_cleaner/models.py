from dataclasses import asdict, dataclass, field
from pathlib import Path
import sys


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def vendor_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "vendor"
    return resource_root() / "vendor"


@dataclass
class Options:
    source_mode: str = "all"
    ocr: bool = True
    correct_answers: bool = True
    skip_a3: bool = True
    remove_last_slide: bool = True


@dataclass
class Record:
    source: str
    status: str = "处理中"
    outputs: list[str] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    watermark_count: int = 0
    source_count: int = 0

    def to_dict(self):
        return asdict(self)


class Cancelled(Exception):
    pass
