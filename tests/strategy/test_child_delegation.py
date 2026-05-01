# The MIT License (MIT)
# Copyright (c) 2026 val-bittensor contributors

# Unit tests for child-hotkey delegation functionality.

from unittest.mock import MagicMock, patch

import pytest
from strategy.child_delegation import (
    ChildAllocation,
    apply_children,
    plan_allocation,
    query_children,
    query_delegated,
)
from strategy.scoring import SubnetMetrics


class TestQueryChildren:
    """Tests for query_children function."""

    @patch("strategy.child_delegation.bt.Subtensor")
    def test_query_children_success(self, mock_subtensor_class):
        """Should return list of ChildAllocation on successful query."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor

        # Mock successful get_children response
        mock_subtensor.get_children.return_value = (
            True,
            [(0.5, "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"),
             (0.5, "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY")],
            "Success",
        )

        result = query_children(mock_subtensor, "parent_hotkey", 1)

        assert len(result) == 2
        assert result[0].hotkey_ss58 == "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"
        assert result[0].proportion == 0.5
        assert result[1].proportion == 0.5

    @patch("strategy.child_delegation.bt.Subtensor")
    def test_query_children_failure(self, mock_subtensor_class):
        """Should return empty list on failed query."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor

        mock_subtensor.get_children.return_value = (False, [], "Not found")

        result = query_children(mock_subtensor, "parent_hotkey", 1)

        assert result == []

    @patch("strategy.child_delegation.bt.Subtensor")
    def test_query_children_exception(self, mock_subtensor_class):
        """Should return empty list on exception."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor

        mock_subtensor.get_children.side_effect = Exception("RPC error")

        result = query_children(mock_subtensor, "parent_hotkey", 1)

        assert result == []


class TestQueryDelegated:
    """Tests for query_delegated function."""

    @patch("strategy.child_delegation.bt.Subtensor")
    def test_query_delegated_success(self, mock_subtensor_class):
        """Should return DelegatedInfo on successful query."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor

        mock_delegated_info = MagicMock()
        mock_delegated_info.total_stake = 1000.0
        mock_subtensor.get_delegated.return_value = [mock_delegated_info]

        result = query_delegated(mock_subtensor, "coldkey_ss58")

        assert result is not None
        assert result.total_stake == 1000.0

    @patch("strategy.child_delegation.bt.Subtensor")
    def test_query_delegated_not_found(self, mock_subtensor_class):
        """Should return None when no delegations found."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor

        mock_subtensor.get_delegated.return_value = []

        result = query_delegated(mock_subtensor, "coldkey_ss58")

        assert result is None

    @patch("strategy.child_delegation.bt.Subtensor")
    def test_query_delegated_exception(self, mock_subtensor_class):
        """Should return None on exception."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor

        mock_subtensor.get_delegated.side_effect = Exception("RPC error")

        result = query_delegated(mock_subtensor, "coldkey_ss58")

        assert result is None


class TestPlanAllocation:
    """Tests for plan_allocation function."""

    def test_plan_allocation_basic(self):
        """Should allocate proportions that sum to 1.0 per subnet."""
        # Create subnet metrics
        metrics = [
            SubnetMetrics(
                netuid=1,
                name="subnet1",
                subnet_emission_tao=1000,
                saturation=0.5,
                validator_permit_threshold_tao=100,
                top_validator_stake_tao=1000,
                registration_cost_tao=100,
                alpha_price_tao=1.0,
                num_uids=32,
                max_uids=64,
                max_validators=64,
            ),
            SubnetMetrics(
                netuid=2,
                name="subnet2",
                subnet_emission_tao=500,
                saturation=0.7,
                validator_permit_threshold_tao=100,
                top_validator_stake_tao=800,
                registration_cost_tao=100,
                alpha_price_tao=1.0,
                num_uids=45,
                max_uids=64,
                max_validators=64,
            ),
        ]

        child_hotkeys = ["child1", "child2"]
        allocation = plan_allocation(metrics, child_hotkeys, 1000.0)

        assert 1 in allocation
        assert 2 in allocation

        # Each child gets 1.0 proportion (100% of that subnet's stake)
        assert allocation[1][0].proportion == pytest.approx(1.0)
        assert allocation[2][0].proportion == pytest.approx(1.0)

    def test_plan_allocation_fewer_hotkeys_than_subnets(self):
        """Should allocate only to top-N subnets when hotkeys < subnets."""
        metrics = [
            SubnetMetrics(
                netuid=i,
                name=f"subnet{i}",
                subnet_emission_tao=1000 - i * 100,
                saturation=0.5,
                validator_permit_threshold_tao=100,
                top_validator_stake_tao=1000,
                registration_cost_tao=100,
                alpha_price_tao=1.0,
                num_uids=32,
                max_uids=64,
                max_validators=64,
            )
            for i in range(1, 6)  # 5 subnets
        ]

        child_hotkeys = ["child1", "child2"]  # Only 2 hotkeys
        allocation = plan_allocation(metrics, child_hotkeys, 1000.0)

        # Should only allocate to top 2 subnets by emission
        assert len(allocation) == 2
        assert 1 in allocation  # Highest emission
        assert 2 in allocation  # Second highest

    def test_plan_allocation_empty_metrics(self):
        """Should return empty dict for empty subnet metrics."""
        result = plan_allocation([], ["child1"], 1000.0)
        assert result == {}

    def test_plan_allocation_empty_hotkeys(self):
        """Should return empty dict for empty child hotkeys."""
        metrics = [SubnetMetrics(
            netuid=1,
            name="subnet1",
            subnet_emission_tao=1000,
            saturation=0.5,
            validator_permit_threshold_tao=100,
            top_validator_stake_tao=1000,
            registration_cost_tao=100,
            alpha_price_tao=1.0,
            num_uids=32,
            max_uids=64,
            max_validators=64,
        )]
        result = plan_allocation(metrics, [], 1000.0)
        assert result == {}

    def test_plan_allocation_zero_stake(self):
        """Should return empty dict for zero available stake."""
        metrics = [SubnetMetrics(
            netuid=1,
            name="subnet1",
            subnet_emission_tao=1000,
            saturation=0.5,
            validator_permit_threshold_tao=100,
            top_validator_stake_tao=1000,
            registration_cost_tao=100,
            alpha_price_tao=1.0,
            num_uids=32,
            max_uids=64,
            max_validators=64,
        )]
        result = plan_allocation(metrics, ["child1"], 0.0)
        assert result == {}

    def test_plan_allocation_skips_closed_registration(self):
        """Should skip subnets with closed registration."""
        metrics = [
            SubnetMetrics(
                netuid=1,
                name="subnet1",
                subnet_emission_tao=1000,
                saturation=0.5,
                validator_permit_threshold_tao=100,
                top_validator_stake_tao=1000,
                registration_cost_tao=100,
                alpha_price_tao=1.0,
                num_uids=32,
                max_uids=64,
                max_validators=64,
                notes=["closed_to_registration"],  # Closed
            ),
            SubnetMetrics(
                netuid=2,
                name="subnet2",
                subnet_emission_tao=500,
                saturation=0.5,
                validator_permit_threshold_tao=100,
                top_validator_stake_tao=800,
                registration_cost_tao=100,
                alpha_price_tao=1.0,
                num_uids=32,
                max_uids=64,
                max_validators=64,
                notes=[],  # Open
            ),
        ]

        allocation = plan_allocation(metrics, ["child1"], 1000.0)

        # Should only allocate to netuid 2 (open)
        assert 1 not in allocation
        assert 2 in allocation


class TestApplyChildren:
    """Tests for apply_children function."""

    @patch("builtins.input", return_value="n")
    @patch("strategy.child_delegation.bt.Subtensor")
    @patch("strategy.child_delegation.Console")
    def test_apply_children_dry_run(self, mock_console_class, mock_subtensor_class, mock_input):
        """Should print plan without executing in dry-run mode."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        children = [
            ChildAllocation(hotkey_ss58="child1", proportion=0.5),
            ChildAllocation(hotkey_ss58="child2", proportion=0.5),
        ]
        wallet = MagicMock()
        wallet.hotkey.ss58 = "parent_hotkey"

        result = apply_children(wallet, mock_subtensor, 1, children, dry_run=True)

        assert result is None
        mock_subtensor.set_children.assert_not_called()

    @patch("builtins.input", return_value="y")
    @patch("strategy.child_delegation.bt.Subtensor")
    @patch("strategy.child_delegation.Console")
    @patch("strategy.child_delegation.bt.logging")
    def test_apply_children_user_confirms(self, mock_logging, mock_console_class, mock_subtensor_class, mock_input):
        """Should execute when user confirms."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_extrinsic = MagicMock()
        mock_extrinsic.hash = "0x123"
        mock_subtensor.set_children.return_value = mock_extrinsic

        children = [
            ChildAllocation(hotkey_ss58="child1", proportion=1.0),
        ]
        wallet = MagicMock()
        wallet.hotkey.ss58 = "parent_hotkey"

        result = apply_children(wallet, mock_subtensor, 1, children, dry_run=False)

        assert result == mock_extrinsic
        mock_subtensor.set_children.assert_called_once()

    @patch("builtins.input", return_value="n")
    @patch("strategy.child_delegation.bt.Subtensor")
    @patch("strategy.child_delegation.Console")
    @patch("strategy.child_delegation.bt.logging")
    def test_apply_children_user_aborts(self, mock_logging, mock_console_class, mock_subtensor_class, mock_input):
        """Should not execute when user aborts."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        children = [
            ChildAllocation(hotkey_ss58="child1", proportion=1.0),
        ]
        wallet = MagicMock()
        wallet.hotkey.ss58 = "parent_hotkey"

        result = apply_children(wallet, mock_subtensor, 1, children, dry_run=False)

        assert result is None
        mock_subtensor.set_children.assert_not_called()

    @patch("builtins.input", return_value="y")
    @patch("strategy.child_delegation.bt.Subtensor")
    @patch("strategy.child_delegation.Console")
    @patch("strategy.child_delegation.bt.logging")
    def test_apply_children_on_error(self, mock_logging, mock_console_class, mock_subtensor_class, mock_input):
        """Should return None on chain error."""
        mock_subtensor = MagicMock()
        mock_subtensor_class.return_value = mock_subtensor
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_subtensor.set_children.side_effect = Exception("Chain error")

        children = [
            ChildAllocation(hotkey_ss58="child1", proportion=1.0),
        ]
        wallet = MagicMock()
        wallet.hotkey.ss58 = "parent_hotkey"

        result = apply_children(wallet, mock_subtensor, 1, children, dry_run=False)

        assert result is None
