import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent / "harness"
VENDOR = HERE / "eval_qc_env" / "_vendor"
FILES = ("bm25.py", "text.py", "env/core.py", "env/tickets.py", "env/dataqc.py", "env/retrieval.py")


def pairs():
    return [(HARNESS / f, VENDOR / f) for f in FILES]


def out_of_sync():
    return [str(dst.relative_to(HERE)) for src, dst in pairs()
            if not dst.exists() or src.read_bytes() != dst.read_bytes()]


def sync():
    for d in (VENDOR, VENDOR / "env"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("", encoding="utf-8")
    for src, dst in pairs():
        shutil.copyfile(src, dst)
    return [str(dst.relative_to(HERE)) for _, dst in pairs()]


if __name__ == "__main__":
    if "--check" in sys.argv:
        stale = out_of_sync()
        print("in sync" if not stale else f"out of sync: {stale}")
        sys.exit(1 if stale else 0)
    print("copied:", ", ".join(sync()))
