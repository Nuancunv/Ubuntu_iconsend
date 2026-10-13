"""Application entry point; CLI flags are for integration and diagnostics."""

import argparse
import json
import sys
from pathlib import Path

from .core import ShortcutError, create_shortcut, inspect_launcher, list_applications


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ubuntu_iconsend — Send Shortcut to Desktop")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="List validated installed applications as JSON")
    group.add_argument("--create", metavar="ID_OR_PATH", help="Create a shortcut for a trusted application")
    group.add_argument("--send-files", nargs="+", metavar="FILE", help="Graphical create/review for Nautilus")
    group.add_argument("--check", action="store_true", help="Report environment and dependencies")
    args = parser.parse_args(argv)
    try:
        if args.check:
            from .diagnostics import report
            print(json.dumps(report(), ensure_ascii=False, indent=2))
            return 0
        if args.list:
            print(json.dumps([{"id": a.app_id, "name": a.name, "file": str(a.source), "origin": a.origin, "trusted": a.trusted}
                              for a in list_applications()], ensure_ascii=False, indent=2))
            return 0
        if args.create:
            if Path(args.create).is_absolute() or "/" in args.create:
                record = inspect_launcher(args.create)
            else:
                record = next((a for a in list_applications() if a.app_id == args.create), None)
                if record is None:
                    raise ShortcutError("Application not found / 未找到应用：" + args.create)
            print(create_shortcut(record))
            return 0
        from .gui import run
        return run(args.send_files)
    except (ShortcutError, ImportError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
