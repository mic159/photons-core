# coding: spec

from photons_themes.appliers import types

from photons_app.test_helpers import TestCase

describe TestCase, "types":
    it "has 0d, 1d and 2d for each type":
        for typ, appliers in types.items():
            assert "0d" in appliers
            assert "1d" in appliers
            assert "2d" in appliers
