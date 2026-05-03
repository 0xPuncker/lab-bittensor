"""Smoke tests for lab-bittensor.

Until the incentive mechanism is defined, these tests just verify that the
inherited template + bittensor 10 SDK imports + the Dummy wire protocol all
work. We do NOT exercise the mock-mode validator forward path because
bittensor 10.3.0's MockSubtensor has an upstream bug:
`neuron_for_uid_lite` references `NeuronInfo.rank` which is absent from the
current NeuronInfo (file: bittensor/utils/mock/subtensor_mock.py:985).

When upstream fixes that, expand here to a full mock forward-step test —
tracked in `.specs/project/STATE.md → Deferred Ideas`.
"""

from __future__ import annotations

from template.protocol import Dummy


def test_template_imports() -> None:
    """Top-level template + neurons imports work after the bittensor 10 API drift fixes.

    If this test fails, the basic `from X import Y` paths in the package
    are broken — likely another lowercase-class symbol that needs renaming.
    """
    import neurons.validator  # noqa: F401
    from template.base.validator import BaseValidatorNeuron  # noqa: F401
    from template.validator import forward as forward_module  # noqa: F401
    from template.validator.reward import get_rewards, reward

    assert callable(reward), "reward() must be callable"
    assert callable(get_rewards), "get_rewards() must be callable"


def test_dummy_synapse_round_trip() -> None:
    """The placeholder Dummy wire protocol round-trips its int payload."""
    synapse = Dummy(dummy_input=5)
    assert synapse.dummy_input == 5
    assert synapse.dummy_output is None

    synapse.dummy_output = 10
    assert synapse.deserialize() == 10


def test_dummy_reward_logic() -> None:
    """The placeholder reward function returns 1.0 iff response == 2 * query."""
    from template.validator.reward import reward

    assert reward(query=5, response=10) == 1.0
    assert reward(query=5, response=11) == 0
    assert reward(query=0, response=0) == 1.0
