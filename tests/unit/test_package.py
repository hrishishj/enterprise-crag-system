import importlib

import pytest

LAYERS = ["domain", "core", "adapters", "pipelines", "apps"]


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_packages_import(layer):
    assert importlib.import_module(f"crag.{layer}")
