"""Load the parts catalog and kit inventories from data/."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from bobthebuilder.inventory.parts import Inventory, Part

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class Catalog:
    def __init__(self, parts: list[Part]):
        self._parts = {p.ldraw_id: p for p in parts}

    def get(self, ldraw_id: str) -> Part:
        try:
            return self._parts[ldraw_id]
        except KeyError:
            raise KeyError(f"Unknown part {ldraw_id!r}; add it to data/parts.json") from None

    def __contains__(self, ldraw_id: str) -> bool:
        return ldraw_id in self._parts

    def all(self) -> list[Part]:
        return list(self._parts.values())


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    raw = json.loads((DATA_DIR / "parts.json").read_text())
    return Catalog([Part(**p) for p in raw["parts"]])


@lru_cache(maxsize=8)
def load_inventory(kit_id: str) -> Inventory:
    path = DATA_DIR / "inventories" / f"{kit_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No inventory for kit {kit_id!r} at {path}")
    inv = Inventory(**json.loads(path.read_text()))
    catalog = load_catalog()
    unknown = [l.ldraw_id for l in inv.lines if l.ldraw_id not in catalog]
    if unknown:
        raise ValueError(f"Inventory {kit_id} references parts missing from catalog: {unknown}")
    return inv
