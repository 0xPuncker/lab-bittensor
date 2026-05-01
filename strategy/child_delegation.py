# The MIT License (MIT)
# Copyright (c) 2026 val-bittensor contributors

# Child-hotkey delegation management tooling.
# Provides read queries, allocation planning, and dry-run execution for validator child-hotkey strategies.

import argparse
from dataclasses import dataclass
from typing import Optional

import bittensor as bt
from bittensor.core.types import ExtrinsicResponse
from rich.console import Console
from rich.table import Table

from strategy.scoring import SubnetMetrics


@dataclass(frozen=True)
class ChildAllocation:
    """A single child-hotkey allocation with its proportion."""
    hotkey_ss58: str
    proportion: float  # 0.0 to 1.0, sum across a subnet should equal 1.0


@dataclass(frozen=True)
class AllocationPlan:
    """Complete allocation plan for a subnet."""
    netuid: int
    children: list[ChildAllocation]


def query_children(
    subtensor: bt.Subtensor,
    hotkey_ss58: str,
    netuid: int,
) -> list[ChildAllocation]:
    """Query current child-hotkey allocations for a hotkey on a subnet.

    Args:
        subtensor: Connected Subtensor instance
        hotkey_ss58: Parent hotkey SS58 address
        netuid: Subnet netuid

    Returns:
        List of ChildAllocation for the hotkey on this subnet. Empty if none found.
    """
    try:
        success, children_list, message = subtensor.get_children(
            hotkey_ss58=hotkey_ss58,
            netuid=netuid,
        )
        if not success:
            bt.logging.debug(f"get_children failed: {message}")
            return []

        return [
            ChildAllocation(hotkey_ss58=child_hotkey, proportion=proportion)
            for proportion, child_hotkey in children_list
        ]
    except Exception as e:
        bt.logging.error(f"Failed to query children for {hotkey_ss58} on netuid {netuid}: {e}")
        return []


def query_delegated(
    subtensor: bt.Subtensor,
    coldkey_ss58: str,
) -> Optional["bt.DelegatedInfo"]:
    """Query delegated stake information for a coldkey.

    Args:
        subtensor: Connected Subtensor instance
        coldkey_ss58: Coldkey SS58 address

    Returns:
        DelegatedInfo if found, None on error.
    """
    try:
        delegated_list = subtensor.get_delegated(coldkey_ss58=coldkey_ss58)
        if not delegated_list:
            return None
        # Return the first (typically only one) DelegatedInfo
        return delegated_list[0]
    except Exception as e:
        bt.logging.error(f"Failed to query delegated for {coldkey_ss58}: {e}")
        return None


def plan_allocation(
    subnet_metrics: list[SubnetMetrics],
    child_hotkeys: list[str],
    available_stake: float,
) -> dict[int, list[ChildAllocation]]:
    """Plan optimal child-hotkey allocation across subnets.

    Prioritizes high-emission / low-competition subnets. Each subnet gets one child
    with proportion 1.0 (meaning that child receives 100% of that subnet's stake).

    The actual stake distribution across subnets is implicit in which subnets you
    choose to register children on.

    Args:
        subnet_metrics: List of subnet metrics from evaluator (sorted by score desc)
        child_hotkeys: Available child hotkey SS58 addresses
        available_stake: Total stake available to allocate (in TAO)

    Returns:
        Mapping of netuid -> list of ChildAllocation. Empty if no valid allocations.
    """
    if not subnet_metrics or not child_hotkeys or available_stake <= 0:
        return {}

    # Filter to subnets where registration is possible (not closed)
    # and sort by emission desc (prioritize high-emission subnets)
    valid_subnets = [
        m for m in subnet_metrics
        if "closed_to_registration" not in m.notes and m.subnet_emission_tao > 0
    ]

    if not valid_subnets:
        bt.logging.warning("No valid subnets for allocation (all closed or zero emission)")
        return {}

    # Allocate to top min(len(child_hotkeys), len(valid_subnets)) subnets
    num_allocations = min(len(child_hotkeys), len(valid_subnets))
    top_subnets = valid_subnets[:num_allocations]

    # Each child gets 100% of its subnet's stake (proportion = 1.0)
    allocation: dict[int, list[ChildAllocation]] = {}
    for i, subnet in enumerate(top_subnets):
        if i < len(child_hotkeys):
            child_hotkey = child_hotkeys[i]
            allocation[subnet.netuid] = [
                ChildAllocation(hotkey_ss58=child_hotkey, proportion=1.0)
            ]

    return allocation


def apply_children(
    wallet: bt.Wallet,
    subtensor: bt.Subtensor,
    netuid: int,
    children: list[ChildAllocation],
    dry_run: bool = False,
) -> Optional[ExtrinsicResponse]:
    """Apply child-hotkey allocation on-chain.

    Args:
        wallet: Wallet to sign the transaction
        subtensor: Connected Subtensor instance
        netuid: Subnet netuid
        children: List of ChildAllocation to apply
        dry_run: If True, print plan and return None without executing

    Returns:
        ExtrinsicResponse if executed, None if dry-run or failed.
    """
    # Convert to list[(proportion, hotkey_ss58)] format for bittensor
    children_tuples = [(c.proportion, c.hotkey_ss58) for c in children]

    if dry_run:
        bt.logging.info(f"[DRY-RUN] Would set children for netuid {netuid}:")
        for prop, hotkey in children_tuples:
            bt.logging.info(f"  {prop:.4f} -> {hotkey}")
        return None

    # Confirmation prompt
    console = Console()
    table = Table(title=f"Proposed children for netuid {netuid}")
    table.add_column("Proportion", justify="right")
    table.add_column("Child Hotkey")

    for prop, hotkey in children_tuples:
        table.add_row(f"{prop:.4f}", hotkey)

    console.print(table)

    response = input("Apply this allocation? (y/n): ").strip().lower()
    if response != "y":
        bt.logging.info("Aborted by user")
        return None

    try:
        extrinsic = subtensor.set_children(
            wallet=wallet,
            netuid=netuid,
            hotkey_ss58=wallet.hotkey.ss58,
            children=children_tuples,
            wait_for_inclusion=False,
            wait_for_finalization=False,
        )
        bt.logging.success(f"set_children submitted: {extrinsic.hash}")
        return extrinsic
    except Exception as e:
        bt.logging.error(f"Failed to set children for netuid {netuid}: {e}")
        return None


def _format_children_table(children: list[ChildAllocation]) -> Table:
    """Format a list of ChildAllocation as a Rich table."""
    table = Table(title="Child Hotkey Allocations")
    table.add_column("Proportion", justify="right")
    table.add_column("Child Hotkey")

    for child in children:
        table.add_row(f"{child.proportion:.4f}", child.hotkey_ss58)

    return table


def main() -> None:
    """CLI entry point for child-hotkey delegation management."""
    parser = argparse.ArgumentParser(
        description="Manage child-hotkey delegation for Bittensor validators",
    )
    parser.add_argument(
        "--network",
        choices=["finney", "test"],
        default="finney",
        help="Bittensor network (default: finney)",
    )
    parser.add_argument(
        "--wallet-name",
        required=True,
        help="Wallet name (coldkey)",
    )
    parser.add_argument(
        "--hotkey",
        default="default",
        help="Hotkey name (default: default)",
    )
    parser.add_argument(
        "--query",
        type=int,
        metavar="NETUID",
        help="Query current children for a specific subnet",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Generate allocation plan (requires --child-hotkeys or --evaluator-json)",
    )
    parser.add_argument(
        "--child-hotkeys",
        nargs="+",
        help="Child hotkey SS58 addresses for allocation",
    )
    parser.add_argument(
        "--evaluator-json",
        help="Path to subnet-evaluator JSON output for planning",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply allocation plan (requires --plan)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without executing (use with --apply)",
    )
    parser.add_argument(
        "--stake",
        type=float,
        default=1000.0,
        help="Available stake for planning (default: 1000 TAO)",
    )

    args = parser.parse_args()

    # Initialize subtensor connection
    bt.logging.info(f"Connecting to {args.network} network...")
    subtensor = bt.Subtensor(network=args.network)

    # Load wallet
    wallet = bt.Wallet(name=args.wallet.name, hotkey=args.hotkey)
    if not wallet.exists():
        bt.logging.error(f"Wallet {args.wallet.name}/{args.hotkey} not found")
        return

    bt.logging.info(f"Using wallet: {wallet.name}/{wallet.hotkey.ss58}")

    console = Console()

    # Query mode
    if args.query is not None:
        children = query_children(subtensor, wallet.hotkey.ss58, args.query)
        if children:
            table = _format_children_table(children)
            console.print(table)
        else:
            bt.logging.info(f"No children found for netuid {args.query}")
        return

    # Plan mode
    if args.plan:
        # Load subnet metrics
        subnet_metrics: list[SubnetMetrics] = []

        if args.evaluator_json:
            import json

            bt.logging.info(f"Loading evaluator output from {args.evaluator_json}")
            with open(args.evaluator_json) as f:
                data = json.load(f)
            # Convert evaluator JSON to SubnetMetrics
            # Assuming JSON format matches SubnetMetrics fields
            for item in data.get("subnets", []):
                subnet_metrics.append(SubnetMetrics(**item))
        else:
            bt.logging.warning("No evaluator JSON provided, using dummy metrics")
            # Fallback: query a few subnets directly
            # This is a simple fallback for testing without evaluator output
            pass

        child_hotkeys = args.child_hotkeys or []
        if not child_hotkeys:
            bt.logging.error("--child-hotkeys required for planning (or use --evaluator-json with embedded hotkeys)")
            return

        allocation = plan_allocation(subnet_metrics, child_hotkeys, args.stake)

        if not allocation:
            bt.logging.info("No allocation plan generated")
            return

        # Display plan
        for netuid, children in allocation.items():
            table = Table(title=f"Allocation Plan for Netuid {netuid}")
            table.add_column("Proportion", justify="right")
            table.add_column("Child Hotkey")

            for child in children:
                table.add_row(f"{child.proportion:.4f}", child.hotkey_ss58)

            console.print(table)

        # Apply if requested
        if args.apply:
            for netuid, children in allocation.items():
                result = apply_children(wallet, subtensor, netuid, children, dry_run=args.dry_run)
                if result is None and not args.dry_run:
                    bt.logging.error(f"Failed to apply allocation for netuid {netuid}, stopping")
                    break

        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
