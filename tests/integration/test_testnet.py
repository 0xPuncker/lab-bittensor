"""Integration tests for Bittensor testnet wiring.

SKIPPED BY DEFAULT. Tests run when these env vars are set:

  BT_TESTNET_WALLET   — wallet name under ~/.bittensor/wallets/ (required)
  BT_TESTNET_HOTKEY   — hotkey name under that wallet           (default: "default")
  BT_TESTNET_NETUID   — netuid the wallet is registered to      (required for tests 2 + 3)

Costs: zero TAO. All tests are read-only chain queries against
`bt.Subtensor(network="test")`. No transactions, no weight setting,
no `btcli`. The operator runs `btcli` themselves following
`docs/testnet-validation.md`; these tests verify each milestone they reach.

Why this exists: M0 left the mock-mode code paths green (smoke test) but
never exercised the non-mock branches in `template/base/neuron.py:89-92`
or `template/base/validator.py:62, 92, 272`. These integration tests
catch any remaining bittensor 10 API drift the smoke test couldn't reach.

Run:
    BT_TESTNET_WALLET=mywallet BT_TESTNET_NETUID=1 \\
      python -m pytest tests/integration -v
"""

from __future__ import annotations

import os

# bittensor is a heavy import; module-scope so collection is fast.
import bittensor as bt  # noqa: E402
import pytest

WALLET_NAME = os.environ.get("BT_TESTNET_WALLET")
HOTKEY_NAME = os.environ.get("BT_TESTNET_HOTKEY", "default")
NETUID_ENV = os.environ.get("BT_TESTNET_NETUID")
NETUID = int(NETUID_ENV) if NETUID_ENV else None


# Test gates ------------------------------------------------------------

needs_wallet = pytest.mark.skipif(
    not WALLET_NAME,
    reason="BT_TESTNET_WALLET not set; skipping testnet integration tests",
)
needs_netuid = pytest.mark.skipif(
    NETUID is None,
    reason="BT_TESTNET_NETUID not set; skipping subnet-scoped tests",
)


# Fixtures --------------------------------------------------------------

@pytest.fixture(scope="module")
def subtensor() -> bt.Subtensor:
    """Read-only Subtensor connected to testnet."""
    return bt.Subtensor(network="test")


@pytest.fixture(scope="module")
def wallet() -> bt.Wallet:
    """Operator's testnet wallet, loaded from ~/.bittensor/wallets/<name>/."""
    return bt.Wallet(name=WALLET_NAME, hotkey=HOTKEY_NAME)


# Tests -----------------------------------------------------------------

@needs_wallet
def test_subtensor_connects(subtensor: bt.Subtensor) -> None:
    """The bittensor 10 SDK can connect to testnet and read chain state."""
    block = subtensor.get_current_block()
    assert isinstance(block, int), f"get_current_block returned {type(block)}, expected int"
    assert block > 0, f"current block = {block}; testnet chain not advancing?"


@needs_wallet
@needs_netuid
def test_metagraph_loads(subtensor: bt.Subtensor) -> None:
    """The configured netuid has a metagraph with at least one neuron."""
    assert NETUID is not None  # for type-checker; @needs_netuid guards at runtime
    metagraph = subtensor.metagraph(NETUID)
    n = metagraph.n.item()
    assert n > 0, f"metagraph for netuid {NETUID} reports n={n}; subnet empty or wrong netuid"
    assert len(metagraph.hotkeys) == n, (
        f"metagraph.hotkeys length {len(metagraph.hotkeys)} != n {n}; "
        "metagraph appears inconsistent"
    )
    # If we got this far, axons should also be populated:
    assert len(metagraph.axons) == n, (
        f"metagraph.axons length {len(metagraph.axons)} != n {n}"
    )


@needs_wallet
@needs_netuid
def test_wallet_registered(subtensor: bt.Subtensor, wallet: bt.Wallet) -> None:
    """The operator's hotkey is registered to the configured netuid."""
    assert NETUID is not None  # for type-checker
    hotkey_ss58 = wallet.hotkey.ss58_address
    is_registered = subtensor.is_hotkey_registered(
        netuid=NETUID,
        hotkey_ss58=hotkey_ss58,
    )
    assert is_registered, (
        f"hotkey {hotkey_ss58} (wallet={WALLET_NAME}, hotkey={HOTKEY_NAME}) is "
        f"NOT registered on testnet netuid {NETUID}. "
        f"Run `btcli subnet register --netuid {NETUID} --subtensor.network test "
        f"--wallet.name {WALLET_NAME} --wallet.hotkey {HOTKEY_NAME}` first. "
        "See docs/testnet-validation.md."
    )
