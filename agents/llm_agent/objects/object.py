from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Blob:
    instance_id: str
    name: str = ""
    type_hypothesis: str = ""
    colors: list = field(default_factory=list)      # ARC hex chars e.g. ['3', 'e']
    bbox: dict = field(default_factory=dict)         # row_min/max, col_min/max
    cell_count: int = 0
    is_present: bool = True
    last_seen_step: int = 0
    last_seen_bbox: Optional[dict] = None
    disappear_reason: Optional[str] = None
    color_ratios: dict = field(default_factory=dict)  # {"3": 0.6, "0": 0.4}
    clickable: bool = False
    interaction_tested: bool = False

    def center(self) -> tuple:
        return (
            (self.bbox["row_min"] + self.bbox["row_max"]) // 2,
            (self.bbox["col_min"] + self.bbox["col_max"]) // 2,
        )

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "type_hypothesis": self.type_hypothesis,
            "colors": self.colors,
            "bbox": self.bbox,
            "cell_count": self.cell_count,
            "is_present": self.is_present,
            "last_seen_step": self.last_seen_step,
        }
