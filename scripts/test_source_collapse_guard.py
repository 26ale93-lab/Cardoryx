#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

import build_retail_index as builder


def source(name, accepted):
    return {
        "source": name,
        "accepted": accepted,
    }


class SourceCollapseGuardTests(unittest.TestCase):

    def test_blocks_lpp_collapse_to_zero(self):
        previous = {
            "sources": [source("LPP Collecting", 977)]
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"LPP Collecting \(977 -> 0\)",
        ):
            builder.validate_source_collapse(
                previous,
                [source("LPP Collecting", 0)],
            )

    def test_blocks_missing_guarded_source(self):
        previous = {
            "sources": [source("Warcard", 1003)]
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"Warcard \(1003 -> 0\)",
        ):
            builder.validate_source_collapse(
                previous,
                [],
            )

    def test_allows_normal_inventory_change(self):
        result = builder.validate_source_collapse(
            {"sources": [source("LPP Collecting", 977)]},
            [source("LPP Collecting", 901)],
        )

        self.assertTrue(result["comparedToPrevious"])

    def test_allows_small_source_to_reach_zero(self):
        builder.validate_source_collapse(
            {"sources": [source("Collector Store Cards", 5)]},
            [source("Collector Store Cards", 0)],
        )

    def test_allows_new_source_without_history(self):
        builder.validate_source_collapse(
            {"sources": [source("LPP Collecting", 977)]},
            [
                source("LPP Collecting", 900),
                source("New Store", 0),
            ],
        )

    def test_allows_first_build(self):
        result = builder.validate_source_collapse(
            None,
            [source("LPP Collecting", 0)],
        )

        self.assertFalse(result["comparedToPrevious"])

    def test_loads_previous_index(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retail.json"
            expected = {
                "sources": [source("Card Passion", 506)]
            }
            path.write_text(
                json.dumps(expected),
                encoding="utf-8",
            )

            self.assertEqual(
                builder.load_previous_retail_index(path),
                expected,
            )


if __name__ == "__main__":
    unittest.main()
