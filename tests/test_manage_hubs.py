"""Moving a hub under another hub (the card's "Connected to" picker)."""

import pytest

from custom_components.netorbit import manage
from custom_components.netorbit.const import CONF_DEVICES, CONF_HUBS


def _opts():
    def hub(hub_id, name, hub_type, parent):
        return {"id": hub_id, "name": name, "type": hub_type, "parent": parent, "host": None, "mac": None, "source": "manual"}

    return {
        CONF_DEVICES: {},
        CONF_HUBS: [
            hub("gateway", "Router", "router", None),
            hub("core", "Core switch", "switch", "gateway"),
            hub("office", "Office switch", "switch", "core"),
            hub("hall", "Hall AP", "access_point", "gateway"),
        ],
    }


def _parent(opts, hub_id):
    return manage.hub_by_id(opts, hub_id)["parent"]


def test_reparent_is_saved_and_locked():
    opts = _opts()
    manage.update_hub(opts, "office", parent="hall")
    assert _parent(opts, "office") == "hall"
    assert manage.hub_by_id(opts, "office")["parent_locked"] is True


def test_reparent_to_router():
    opts = _opts()
    manage.update_hub(opts, "office", parent="gateway")
    assert _parent(opts, "office") == "gateway"


def test_hub_cannot_go_under_itself():
    opts = _opts()
    with pytest.raises(manage.ManageError, match="cannot connect through itself"):
        manage.update_hub(opts, "core", parent="core")
    assert _parent(opts, "core") == "gateway"


def test_hub_cannot_go_under_its_own_descendant():
    opts = _opts()
    with pytest.raises(manage.ManageError, match="cannot connect through itself"):
        manage.update_hub(opts, "core", parent="office")
    assert _parent(opts, "core") == "gateway"
    assert _parent(opts, "office") == "core"


def test_unknown_parent_rejected():
    opts = _opts()
    with pytest.raises(manage.ManageError, match="No hub called nowhere"):
        manage.update_hub(opts, "office", parent="nowhere")
    assert _parent(opts, "office") == "core"


def test_hub_id_beats_another_hubs_name():
    """The card sends hub ids. A hub renamed to what another hub's id is must not steal the lookup."""
    from types import SimpleNamespace

    from custom_components.netorbit.coordinator import NetOrbitCoordinator

    hubs = [
        {"id": "gateway", "name": "Router"},
        {"id": "ap", "name": "Garage"},
        {"id": "garage", "name": "AP"},
    ]
    coord = SimpleNamespace(opts={CONF_HUBS: hubs}, _seen={})
    assert NetOrbitCoordinator.resolve_hub(coord, "garage") == "garage"
    assert NetOrbitCoordinator.resolve_hub(coord, "hub:ap") == "ap"
    assert NetOrbitCoordinator.resolve_hub(coord, "Garage") == "ap"
