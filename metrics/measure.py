"""Script de métrica de acoplamento (Main Sequence: Ca, Ce, I, A, D).

Régua fixa (ver documentacao/specs.md, R3 — não alterar sem alterar a régua
para todo mundo):

- Componente: cada módulo .py do pacote medido, incluindo subpastas,
  identificado pelo caminho com pontos relativo à raiz do pacote
  (ex.: "adapters.gateway"), exceto __init__.py.
- Dependência: um import (relativo ou absoluto) que resolve para outro
  componente do próprio pacote; bibliotecas externas e da stdlib não contam.
- Ca = nº de componentes que importam este; Ce = nº que este importa.
- I = Ce / (Ce + Ca), ou 0 quando os dois são zero.
- A = nº de classes abstratas (typing.Protocol ou abc.ABC) / total de
  classes do módulo, ou 0 quando o módulo não tem classes.
- D = |A + I - 1|.
- Arredondamento: 2 casas decimais.

Uso:
    python metrics/measure.py <caminho-do-pacote> --out metrics/results/<nome>.csv

Gera <nome>.csv (cabeçalho exato: component,ca,ce,i,a,d) e <nome>.png
(gráfico A x I com a Main Sequence) no mesmo diretório do --out.
"""
import argparse
import ast
import csv
from pathlib import Path


def iter_component_files(package_root: Path):
    """Produz (dotted_name, file_path) para cada módulo do pacote, exceto __init__.py."""
    for file_path in sorted(package_root.rglob("*.py")):
        if file_path.name == "__init__.py":
            continue
        relative = file_path.relative_to(package_root).with_suffix("")
        dotted_name = ".".join(relative.parts)
        yield dotted_name, file_path


def resolve_import_targets(node: ast.AST, module_full_parts: list[str], package_name: str) -> list[str]:
    """Resolve um nó de import (ast.Import ou ast.ImportFrom) para candidatos de
    componente, como dotted names relativos à raiz do pacote medido."""
    targets: list[str] = []

    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            if parts[0] == package_name:
                remainder = parts[1:]
                if remainder:
                    targets.append(".".join(remainder))
        return targets

    if isinstance(node, ast.ImportFrom):
        if node.level > 0:
            # Import relativo: level=1 é o pacote que contém o módulo atual.
            base_parts = module_full_parts[: len(module_full_parts) - node.level]
            if node.module:
                targets.append(".".join(base_parts + node.module.split(".")))
            else:
                for alias in node.names:
                    targets.append(".".join(base_parts + [alias.name]))
            return targets

        # Import absoluto: só interessa se referenciar o próprio pacote medido.
        if node.module:
            mod_parts = node.module.split(".")
            if mod_parts[0] == package_name:
                remainder = mod_parts[1:]
                if remainder:
                    targets.append(".".join(remainder))
                else:
                    for alias in node.names:
                        targets.append(alias.name)
        return targets

    return targets


def is_abstract_base(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id in {"Protocol", "ABC"}
    if isinstance(base, ast.Attribute):
        return base.attr in {"Protocol", "ABC"}
    return False


def count_classes(tree: ast.Module) -> tuple[int, int]:
    """Retorna (total_classes, abstract_classes) entre as classes de topo do módulo."""
    total = 0
    abstract = 0
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            total += 1
            if any(is_abstract_base(base) for base in node.bases):
                abstract += 1
    return total, abstract


def measure(package_root: Path) -> list[dict]:
    package_name = package_root.name
    components = dict(iter_component_files(package_root))
    known = set(components)

    ce_targets: dict[str, set[str]] = {name: set() for name in known}
    class_counts: dict[str, tuple[int, int]] = {}

    for dotted_name, file_path in components.items():
        module_full_parts = dotted_name.split(".")
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for candidate in resolve_import_targets(node, module_full_parts, package_name):
                    if candidate in known and candidate != dotted_name:
                        ce_targets[dotted_name].add(candidate)

        class_counts[dotted_name] = count_classes(tree)

    ca_sources: dict[str, set[str]] = {name: set() for name in known}
    for dotted_name, targets in ce_targets.items():
        for target in targets:
            ca_sources[target].add(dotted_name)

    rows = []
    for dotted_name in sorted(known):
        ce = len(ce_targets[dotted_name])
        ca = len(ca_sources[dotted_name])
        i = 0.0 if (ce + ca) == 0 else ce / (ce + ca)

        total_classes, abstract_classes = class_counts[dotted_name]
        a = 0.0 if total_classes == 0 else abstract_classes / total_classes

        d = abs(a + i - 1)

        rows.append({
            "component": dotted_name,
            "ca": ca,
            "ce": ce,
            "i": round(i, 2),
            "a": round(a, 2),
            "d": round(d, 2),
        })

    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["component", "ca", "ce", "i", "a", "d"])
        writer.writeheader()
        writer.writerows(rows)


def write_plot(rows: list[dict], out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 7))

    xs = [0, 1]
    ys = [1, 0]
    ax.plot(xs, ys, linestyle="--", color="gray", label="Main Sequence (D=0)")

    seen_at_point: dict[tuple[float, float], int] = {}
    for row in rows:
        i, a = row["i"], row["a"]
        in_pain_zone = a < 0.5 and i < 0.5 and row["d"] >= 0.5
        color = "crimson" if in_pain_zone else "steelblue"
        ax.scatter(i, a, color=color, zorder=3)

        stack_index = seen_at_point.get((i, a), 0)
        seen_at_point[(i, a)] = stack_index + 1
        ax.annotate(row["component"], (i, a), textcoords="offset points",
                    xytext=(8, 5 + stack_index * 12), fontsize=8)

    ax.set_xlabel("I (Instabilidade) = Ce / (Ce + Ca)")
    ax.set_ylabel("A (Abstração) = classes abstratas / total de classes")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Main Sequence — acoplamento por componente")
    ax.legend(loc="upper right")
    ax.grid(True, linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_path", type=Path, help="Caminho do pacote a medir (ex.: app/helpdesk)")
    parser.add_argument("--out", type=Path, required=True, help="Caminho do CSV de saída")
    args = parser.parse_args()

    package_root = args.package_path.resolve()
    if not package_root.is_dir():
        raise SystemExit(f"Caminho não é um diretório: {package_root}")

    rows = measure(package_root)

    out_csv = args.out
    write_csv(rows, out_csv)

    out_png = out_csv.with_suffix(".png")
    write_plot(rows, out_png)

    print(f"{len(rows)} componentes medidos.")
    print(f"CSV: {out_csv}")
    print(f"Gráfico: {out_png}")


if __name__ == "__main__":
    main()
