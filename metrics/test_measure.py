"""Teste unitário da régua do script de métrica (ver documentacao/testes.md, §5).

Usa um pacote sintético com Ca/Ce/A conhecidos à mão, para garantir que I, A e D
são calculados conforme a régua antes de rodar sobre app/helpdesk/ de verdade.
"""
from pathlib import Path

from measure import measure


def write(root: Path, relative_path: str, content: str) -> None:
    file_path = root / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def test_synthetic_package_matches_hand_calculated_metrics(tmp_path: Path):
    root = tmp_path / "pkg"

    # "core": sem imports internos, sem classes -> Ce=0, A=0.
    write(root, "core.py", "import os\n\nVALUE = 1\n")

    # "ports": define um Protocol (classe abstrata) e uma classe concreta.
    write(root, "ports.py", (
        "from typing import Protocol\n\n"
        "class Repo(Protocol):\n"
        "    def get(self) -> int: ...\n\n"
        "class Config:\n"
        "    pass\n"
    ))

    # "service": importa core (via `from . import core`) e ports (via `from .ports import Repo`).
    write(root, "service.py", (
        "from . import core\n"
        "from .ports import Repo\n\n"
        "def run():\n"
        "    return core.VALUE\n"
    ))

    # "main": importa service (único componente que ninguém mais importa -> Ce alto, Ca=0).
    write(root, "main.py", "from . import service\n")

    # __init__.py não deve virar componente nem contar como dependência.
    write(root, "__init__.py", "from . import main\n")

    rows = {row["component"]: row for row in measure(root)}

    assert set(rows) == {"core", "ports", "service", "main"}

    # core: Ce=0 (só stdlib); Ca=1 (service importa); I = 0/(0+1) = 0.0; A=0 (sem classes).
    assert rows["core"]["ce"] == 0
    assert rows["core"]["ca"] == 1
    assert rows["core"]["i"] == 0.0
    assert rows["core"]["a"] == 0.0
    assert rows["core"]["d"] == 1.0

    # ports: Ce=0; Ca=1 (service importa); A = 1 abstrata / 2 classes = 0.5.
    assert rows["ports"]["ce"] == 0
    assert rows["ports"]["ca"] == 1
    assert rows["ports"]["a"] == 0.5
    assert rows["ports"]["i"] == 0.0
    assert rows["ports"]["d"] == 0.5

    # service: Ce=2 (core, ports); Ca=1 (main importa); I = 2/3 = 0.67; A=0.
    assert rows["service"]["ce"] == 2
    assert rows["service"]["ca"] == 1
    assert rows["service"]["i"] == round(2 / 3, 2)
    assert rows["service"]["a"] == 0.0

    # main: Ce=1 (service); Ca=0 (ninguém importa main); I = 1/1 = 1.0; A=0; D=0.0.
    assert rows["main"]["ce"] == 1
    assert rows["main"]["ca"] == 0
    assert rows["main"]["i"] == 1.0
    assert rows["main"]["d"] == 0.0


def test_component_with_no_dependencies_and_no_importers_has_zero_instability(tmp_path: Path):
    root = tmp_path / "pkg"
    write(root, "isolated.py", "VALUE = 1\n")

    rows = {row["component"]: row for row in measure(root)}

    assert rows["isolated"]["ce"] == 0
    assert rows["isolated"]["ca"] == 0
    assert rows["isolated"]["i"] == 0.0
