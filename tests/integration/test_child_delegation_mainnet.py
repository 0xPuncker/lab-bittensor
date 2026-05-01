# The MIT License (MIT)
# Copyright (c) 2026 val-bittensor contributors

# Env-gated integration test for child-hotkey delegation against finney mainnet.

import os

import bittensor as bt
import pytest
from strategy.child_delegation import query_children

# Known validator hotkeys on mainnet (high UIDs are typically long-standing validators)
# These are examples; the test will skip if the hotkey has no children
KNOWN_VALIDATOR_HOTKEYS = [
    "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",  # Alice (example)
    "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty",  # Bob (example)
]


@pytest.mark.skipif(
    os.environ.get("BT_RUN_MAINNET_TESTS") != "1",
    reason="BT_RUN_MAINNET_TESTS=1 not set; skipping mainnet integration tests",
)
def test_query_children_against_finney():
    """Integration test: query children for a known validator on finney.

    This test connects to mainnet and queries child-hotkey allocations.
    It passes if either:
    1. The hotkey has children (non-empty result), OR
    2. The hotkey has no children but the query succeeds (empty result is valid)

    The test only fails on RPC errors or malformed responses.
    """
    subtensor = bt.Subtensor(network="finney")

    # Try each known validator until we find one with children or all succeed
    for hotkey_ss58 in KNOWN_VALIDATOR_HOTKEYS:
        # Try querying a few common subnets
        for netuid in [1, 2, 3, 5, 8]:  # Common subnets
            try:
                children = query_children(subtensor, hotkey_ss58, netuid)

                # If we get here without exception, the query succeeded
                # Empty list is valid (hotkey may not have children on this subnet)
                assert isinstance(children, list)

                # If we found children, verify the structure
                if children:
                    for child in children:
                        assert hasattr(child, "hotkey_ss58")
                        assert hasattr(child, "proportion")
                        assert 0.0 <= child.proportion <= 1.0

                    # Found valid children, test passes
                    return

            except Exception as e:
                pytest.fail(f"Failed to query children for {hotkey_ss58} on netuid {netuid}: {e}")

    # If we get here, all queries succeeded but found no children
    # This is still a pass — it means the hotkeys simply don't use child delegation
    pytest.skip("Known validator hotkeys have no children on queried subnets")
