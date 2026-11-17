from pathlib import Path
from shutil import copyfile

root = Path(__file__).resolve().parents[1]
target = root / ".package"
allowed = [
    "app.py",
    "service.py",
    "store.py",
    "engine.py",
    "rate_card.py",
    *[
        "public/" + x
        for x in ("index.html", "studio.js", "style.css", "logo.svg", "care.svg")
    ],
]
(target / "public").mkdir(parents=True, exist_ok=True)
unexpected = [
    x
    for x in target.rglob("*")
    if (x.is_symlink() or x.is_file())
    and x.relative_to(target).as_posix() not in allowed
]
if (
    unexpected
    or target.is_symlink()
    or any((target / x).is_symlink() for x in allowed)
    or (target / "public").is_symlink()
):
    raise SystemExit("Unexpected files in .package; review it before packaging.")
for name in allowed:
    copyfile(root / name, target / name)
print(f"Prepared {len(allowed)} runtime files in .package")
