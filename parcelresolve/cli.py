"""Single-machine demo lifecycle; reset never touches a remote integration."""

import argparse
import fcntl
import json
import os
from pathlib import Path

from .engine import Engine
from .seed import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="ParcelResolve local demo")
    parser.add_argument("command", choices=["seed", "reset", "recover", "contracts"])
    parser.add_argument(
        "--data-dir", type=Path, default=Path(os.getenv("PARCELRESOLVE_DATA_DIR", ".parcelresolve"))
    )
    args = parser.parse_args()
    if args.command == "contracts":
        from .integrations import contract_checks

        print(json.dumps(contract_checks(), indent=2))
        return
    if args.command == "reset":
        args.data_dir.mkdir(parents=True, exist_ok=True)
        with (args.data_dir / ".service.lock").open("a") as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.exit(2, "Stop the local server before resetting its demonstration data.\n")
            # Remove only owned databases and SQLite sidecars; preserve all other files and locks.
            for name in ["ledger.sqlite", "providers.sqlite"]:
                for suffix in ["", "-wal", "-shm"]:
                    (args.data_dir / (name + suffix)).unlink(missing_ok=True)
            engine = Engine(args.data_dir)
            seed_demo(engine)
            print(f"Local demo reset: {len(engine.list_cases())} cases in {args.data_dir}")
        return
    engine = Engine(args.data_dir)
    if args.command == "recover":
        results = engine.recover_pending()
        print(json.dumps([{"id": r["id"], "status": r["status"]} for r in results], indent=2))
    else:
        seed_demo(engine)
        print(f"Local demo ready: {len(engine.list_cases())} cases in {args.data_dir}")


if __name__ == "__main__":
    main()
