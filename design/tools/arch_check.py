#!/usr/bin/env python3
"""施工蓝图（blueprint-kit）的 Python import 检查：代码只能沿图上画了的箭头 import。

配置在 architecture.json 的 arch 字段：
  {"tool": "python", "command": "make arch", "srcRoot": "src/", "package": "app", "external": ["examples/"]}
  srcRoot   源码根目录，包放在 <srcRoot><package>/ 下
  package   本项目的顶层包名
  external  外部客户端目录（只能通过协议访问服务，不能 import 本项目包）
另有 sharedDirs.host（公共目录）和 entryFiles（入口文件 → 允许引用的模块）。

用法：
  python design/tools/arch_check.py                 检查，有违规时退出码为 1
  python design/tools/arch_check.py --json <file>   另外写出实际依赖（给 build.mjs --actual 用）

规则（与图一一对应，只用标准库）：
  1. src/ 下的每个 .py 文件都必须属于图上某个代码模块的目录、公共目录，或 entryFiles 里列出的入口文件。
  2. 模块 A 只能 import：自己、公共目录、图上 A → B 的"代码调用"箭头指向的模块 B。
  3. 公共目录只能 import 公共目录。
  4. external 目录是外部客户端，不能 import 本项目包。
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = json.loads((ROOT / "design" / "architecture.json").read_text(encoding="utf-8"))
ARCH = MODEL.get("arch", {})
PACKAGE_ROOT = ARCH.get("srcRoot", "src/")
SHARED = MODEL["sharedDirs"]["host"]
EXTERNAL = ARCH.get("external", ["examples/"])
ENTRY = MODEL.get("entryFiles", {})
CODE = [m for m in MODEL["modules"] if m.get("code") and m.get("dir")]
BY_ID = {m["id"]: m for m in CODE}


def module_for(rel: str) -> str | None:
    best = None
    for m in CODE:
        if rel.startswith(m["dir"]) and (best is None or len(m["dir"]) > len(best["dir"])):
            best = m
    return best["id"] if best else None


def allowed_targets(mod_id: str) -> set[str]:
    out = {mod_id}
    for e in MODEL["edges"]:
        if e["from"] == mod_id and e["kind"] == "call" and e["to"] in BY_ID:
            out.add(e["to"])
    return out


def dotted_to_path(dotted: str) -> str:
    return PACKAGE_ROOT + dotted.replace(".", "/") + "/"


def file_package(rel: str) -> list[str]:
    # 文件所在的包：pkg/mod.py 和 pkg/__init__.py 都属于 pkg
    return list(Path(rel[len(PACKAGE_ROOT):]).parts[:-1])


def imports_of(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                if not rel.startswith(PACKAGE_ROOT):
                    continue
                pkg = file_package(rel)
                pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                base = ".".join(pkg + ([node.module] if node.module else []))
            found.append(base)
            # from tmcp import sessions  →  也算引用了 tmcp.sessions
            for a in node.names:
                found.append(f"{base}.{a.name}" if base else a.name)
    return found


def main() -> int:
    args = sys.argv[1:]
    json_out = args[args.index("--json") + 1] if "--json" in args else None
    package = ARCH.get("package") or Path(SHARED[len(PACKAGE_ROOT):]).parts[0]
    files = sorted(
        f for d in [PACKAGE_ROOT, *EXTERNAL] if (ROOT / d).exists() for f in (ROOT / d).rglob("*.py")
    )
    violations: list[str] = []
    actual = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if "/." in rel or "__pycache__" in rel:
            continue
        in_src = rel.startswith(PACKAGE_ROOT)
        owner = module_for(rel)
        if in_src and owner is None and not rel.startswith(SHARED) and rel not in ENTRY:
            violations.append(f"{rel}：不在图上任何模块的目录里（no-unmapped-source）")
            continue
        deps = []
        seen: set[str] = set()
        for name in imports_of(f, rel):
            if not (name == package or name.startswith(package + ".")):
                continue
            target_path = dotted_to_path(name)
            target = module_for(target_path)
            is_shared = target_path.startswith(SHARED)
            if target is None and not is_shared:
                continue  # 引用包根（如 tmcp 本身），不构成模块间依赖
            key = target or SHARED
            if key in seen:
                continue
            seen.add(key)
            deps.append({"resolved": target_path})
            if not in_src:
                violations.append(f"{rel} 引用了 {name}：外部客户端目录只能通过协议访问服务，不能 import {package}")
            elif rel.startswith(SHARED):
                if not is_shared:
                    violations.append(f"{rel} 引用了 {name}：公共目录不能引用其他模块（shared-stays-shared）")
            elif rel in ENTRY:
                if not is_shared and target not in ENTRY[rel]:
                    violations.append(f"{rel} 引用了 {name}：入口文件只能引用 {ENTRY[rel] or '无'}")
            elif not is_shared and target not in allowed_targets(owner):
                violations.append(f"{rel} 引用了 {name}：图上没有 [{owner}] → [{target}] 的箭头（only-drawn-calls-{owner}）")
        actual.append({"source": rel, "dependencies": deps})
    if json_out:
        Path(json_out).write_text(json.dumps({"modules": actual}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for v in violations:
        print(f"违规  {v}")
    print(f"检查了 {len(actual)} 个文件，{len(violations)} 处违规。")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
