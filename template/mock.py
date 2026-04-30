import asyncio
import os
import random
import tempfile
import time
from typing import List

import bittensor as bt


def MockWallet(config=None):  # noqa: N802 — PascalCase factory keeps drop-in compat
    """Drop-in replacement for the removed bt.MockWallet (bittensor 10 dropped it).

    Creates a bt.Wallet under a fixed temp dir with auto-generated keypairs.
    Idempotent: subsequent calls reuse the existing keys. Never touches the
    operator's real ~/.bittensor/wallets/.

    The `config` argument is accepted for signature parity with the previous
    bt.MockWallet(config=...) call site in template/base/neuron.py:82, but is
    intentionally ignored — we always use a fixed test path.
    """
    path = os.path.join(tempfile.gettempdir(), "val-bittensor-mock-wallets")
    os.makedirs(path, exist_ok=True)
    wallet = bt.Wallet(name="mock", hotkey="mock", path=path)
    wallet.create_if_non_existent(
        coldkey_use_password=False,
        hotkey_use_password=False,
        suppress=True,
    )
    return wallet


class MockSubtensor(bt.MockSubtensor):
    def __init__(self, netuid, n=16, wallet=None, network="mock"):
        # bittensor 10's MockSubtensor.__init__ accepts (*args, **kwargs) and
        # ignores network. Pass nothing.
        super().__init__()

        # Always create — bittensor 10's `subnet_exists` returns a MagicMock that
        # is truthy by default, so the previous `if not self.subnet_exists(...)`
        # gate skipped creation entirely. `create_subnet` is idempotent here.
        self.create_subnet(netuid)

        # Register ourself (the validator) as a neuron at uid=0
        if wallet is not None:
            self.force_register_neuron(
                netuid=netuid,
                hotkey_ss58=wallet.hotkey.ss58_address,
                coldkey_ss58=wallet.coldkey.ss58_address,
                balance=100000,
                stake=100000,
            )

        # Register n mock neurons who will be miners.
        # bittensor 10 validates ss58 addresses; generate real ones via Keypair.
        for i in range(1, n + 1):
            miner_kp = bt.Keypair.create_from_seed(f"0x{i:064x}")
            self.force_register_neuron(
                netuid=netuid,
                hotkey_ss58=miner_kp.ss58_address,
                coldkey_ss58=miner_kp.ss58_address,  # same kp for both — mock doesn't care
                balance=100000,
                stake=100000,
            )


class MockMetagraph(bt.Metagraph):
    def __init__(self, netuid=1, network="mock", subtensor=None):
        super().__init__(netuid=netuid, network=network, sync=False)

        if subtensor is not None:
            self.subtensor = subtensor
        self.sync(subtensor=subtensor)

        for axon in self.axons:
            axon.ip = "127.0.0.0"
            axon.port = 8091

        bt.logging.info(f"Metagraph: {self}")
        bt.logging.info(f"Axons: {self.axons}")


class MockDendrite(bt.Dendrite):
    """
    Replaces a real bittensor network request with a mock request that just returns some static response for all axons that are passed and adds some random delay.
    """

    def __init__(self, wallet):
        super().__init__(wallet)

    async def forward(
        self,
        axons: List[bt.Axon],
        synapse: bt.Synapse = bt.Synapse(),
        timeout: float = 12,
        deserialize: bool = True,
        run_async: bool = True,
        streaming: bool = False,
    ):
        if streaming:
            raise NotImplementedError("Streaming not implemented yet.")

        async def query_all_axons(streaming: bool):
            """Queries all axons for responses."""

            async def single_axon_response(i, axon):
                """Queries a single axon for a response."""

                start_time = time.time()
                s = synapse.copy()
                # Attach some more required data so it looks real
                s = self.preprocess_synapse_for_request(axon, s, timeout)
                # We just want to mock the response, so we'll just fill in some data
                process_time = random.random()
                if process_time < timeout:
                    s.dendrite.process_time = str(time.time() - start_time)
                    # Update the status code and status message of the dendrite to match the axon
                    # TODO (developer): replace with your own expected synapse data
                    s.dummy_output = s.dummy_input * 2
                    s.dendrite.status_code = 200
                    s.dendrite.status_message = "OK"
                    synapse.dendrite.process_time = str(process_time)
                else:
                    s.dummy_output = 0
                    s.dendrite.status_code = 408
                    s.dendrite.status_message = "Timeout"
                    synapse.dendrite.process_time = str(timeout)

                # Return the updated synapse object after deserializing if requested
                if deserialize:
                    return s.deserialize()
                else:
                    return s

            return await asyncio.gather(
                *(
                    single_axon_response(i, target_axon)
                    for i, target_axon in enumerate(axons)
                )
            )

        return await query_all_axons(streaming)

    def __str__(self) -> str:
        """
        Returns a string representation of the Dendrite object.

        Returns:
            str: The string representation of the Dendrite object in the format "dendrite(<user_wallet_address>)".
        """
        return "MockDendrite({})".format(self.keypair.ss58_address)
