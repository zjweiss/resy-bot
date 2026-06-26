"""CLI entry point.

Usage:
    python -m resy_bot run      [--config config.yaml] [--mode both|snipe|watch]
    python -m resy_bot whoami   [--config config.yaml]   # verify creds, list cards
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .client import ResyClient
from .config import load_config
from .sniper import run_sniper
from .watcher import run_watcher


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def _cmd_run(args) -> int:
    config = load_config(args.config)
    if config.auth.dry_run:
        logging.getLogger("resy_bot").info("DRY RUN — no reservations will be booked.")

    async with ResyClient(
        config.auth.api_key,
        config.auth.auth_token,
        config.auth.payment_method_id,
    ) as client:
        tasks = []
        if args.mode in ("both", "snipe"):
            tasks.append(run_sniper(client, config.snipe, dry_run=config.auth.dry_run))
        if args.mode in ("both", "watch"):
            tasks.append(run_watcher(client, config.watchlist, dry_run=config.auth.dry_run))
        if not tasks:
            print("Nothing to do — check `snipe`/`watchlist` in your config.")
            return 1
        await asyncio.gather(*tasks)
    return 0


async def _cmd_whoami(args) -> int:
    config = load_config(args.config)
    async with ResyClient(
        config.auth.api_key, config.auth.auth_token
    ) as client:
        user = await client.get_user()
        print(f"Logged in as: {user.get('first_name')} {user.get('last_name')} "
              f"<{user.get('em_address')}>")
        methods = user.get("payment_methods", [])
        if methods:
            print("Payment methods (use the id in config.payment_method_id):")
            for m in methods:
                print(f"  id={m.get('id')}  {m.get('display')}  ({m.get('type')})")
        else:
            print("No saved payment methods found.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resy_bot", description="Resy reservation bot")
    parser.add_argument("--config", default="config.yaml", help="path to config YAML")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run sniper and/or watcher")
    run_p.add_argument("--mode", choices=["both", "snipe", "watch"], default="both")

    sub.add_parser("whoami", help="verify credentials and list payment methods")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "run":
            return asyncio.run(_cmd_run(args))
        if args.command == "whoami":
            return asyncio.run(_cmd_whoami(args))
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
