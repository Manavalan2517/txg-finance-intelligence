"""The numbers manifest (§17.3): every number on every slide, with the fact it came from and the text shown."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Entry:
    slide: int
    fact_id: str
    text: str            # exactly what the slide shows
    value: str           # the fact's value when the deck was built
    where: Literal["text", "chart"] = "text"


@dataclass
class Manifest:
    run_id: str
    entries: list[Entry] = field(default_factory=list)

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)

    def on_slide(self, slide: int) -> list[Entry]:
        return [e for e in self.entries if e.slide == slide]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"run_id": self.run_id, "entries": [asdict(e) for e in self.entries]}, indent=1),
                        encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(raw["run_id"], [Entry(**e) for e in raw["entries"]])
