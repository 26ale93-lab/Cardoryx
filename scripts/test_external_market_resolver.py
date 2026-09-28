#!/usr/bin/env python3
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from external_market_resolver import (  # noqa: E402
    DEFAULT_PROVIDER_PRIORITY,
    ExpectedIdentity,
    ProviderCandidate,
    resolve_external_market_estimate,
    validate_candidate,
)

E=ExpectedIdentity(
    tcgplayer_id="201145",
    set_key="SM - Cosmic Eclipse",
    card_number="113",
    printing="Normal",
)

def c(provider, **kw):
    base=dict(
        provider=provider,
        status="EXACT_ONE",
        tcgplayer_id="201145",
        set_key="SM - Cosmic Eclipse",
        card_number="113/236",
        printing="Normal",
        market_language="English",
        condition="Near Mint",
        currency="USD",
        market_price=0.54,
    )
    base.update(kw)
    return ProviderCandidate(**base)


class ResolverPolicyTests(unittest.TestCase):
    def test_default_priority_is_explicit(self):
        self.assertEqual(DEFAULT_PROVIDER_PRIORITY,(
            "pokemonpricetracker","pkmnprices","justtcg"
        ))

    def test_exact_primary_wins_without_averaging(self):
        out=resolve_external_market_estimate(E,[
            c("pokemonpricetracker",market_price=0.55),
            c("pkmnprices",market_price=0.60),
            c("justtcg",market_price=0.54),
        ])
        self.assertTrue(out["available"])
        self.assertEqual(out["provider"],"pokemonpricetracker")
        self.assertEqual(out["price"],"0.55")
        self.assertFalse(out["pricesAveraged"])
        self.assertFalse(out["affectsCollectionValue"])
        self.assertFalse(out["countsAsRetailShop"])

    def test_quota_primary_falls_back(self):
        blocked=ProviderCandidate(provider="pokemonpricetracker",status="QUOTA_BLOCKED")
        out=resolve_external_market_estimate(E,[blocked,c("pkmnprices",market_price=0.60)])
        self.assertTrue(out["available"])
        self.assertEqual(out["provider"],"pkmnprices")

    def test_missing_nm_price_falls_back(self):
        no_price=c("pokemonpricetracker",market_price=None)
        out=resolve_external_market_estimate(E,[no_price,c("justtcg",market_price=0.54)])
        self.assertTrue(out["available"])
        self.assertEqual(out["provider"],"justtcg")

    def test_wrong_tcgplayer_is_rejected(self):
        bad=c("pokemonpricetracker",tcgplayer_id="999999")
        checked=validate_candidate(E,bad)
        self.assertFalse(checked["accepted"])
        self.assertEqual(checked["status"],"IDENTITY_MISMATCH")

    def test_wrong_set_is_rejected(self):
        bad=c("pokemonpricetracker",set_key="Miscellaneous Cards & Products")
        checked=validate_candidate(E,bad)
        self.assertEqual(checked["status"],"SET_MISMATCH")

    def test_wrong_printing_is_rejected(self):
        bad=c("pokemonpricetracker",printing="Reverse Holofoil")
        checked=validate_candidate(E,bad)
        self.assertEqual(checked["status"],"PRINTING_MISMATCH")

    def test_wrong_language_is_rejected(self):
        bad=c("pokemonpricetracker",market_language="Italian")
        checked=validate_candidate(E,bad)
        self.assertEqual(checked["status"],"LANGUAGE_MISMATCH")

    def test_wrong_condition_is_rejected(self):
        bad=c("pokemonpricetracker",condition="Lightly Played")
        checked=validate_candidate(E,bad)
        self.assertEqual(checked["status"],"CONDITION_MISMATCH")

    def test_wrong_currency_is_rejected(self):
        bad=c("pokemonpricetracker",currency="EUR")
        checked=validate_candidate(E,bad)
        self.assertEqual(checked["status"],"CURRENCY_MISMATCH")

    def test_ambiguous_primary_never_contributes_price(self):
        ambiguous=ProviderCandidate(provider="pokemonpricetracker",status="AMBIGUOUS")
        out=resolve_external_market_estimate(E,[ambiguous,c("pkmnprices",market_price=0.60)])
        self.assertTrue(out["available"])
        self.assertEqual(out["provider"],"pkmnprices")
        self.assertIn("pokemonpricetracker:AMBIGUOUS",out["anomalies"])

    def test_all_invalid_returns_unavailable(self):
        out=resolve_external_market_estimate(E,[
            c("pokemonpricetracker",tcgplayer_id="999"),
            ProviderCandidate(provider="pkmnprices",status="MISSING"),
            ProviderCandidate(provider="justtcg",status="UNAVAILABLE"),
        ])
        self.assertFalse(out["available"])
        self.assertEqual(out["display"],"Riferimento mercato esterno non disponibile")

    def test_zero_price_is_valid_but_not_invented(self):
        out=resolve_external_market_estimate(E,[c("justtcg",market_price=0)])
        self.assertTrue(out["available"])
        self.assertEqual(out["price"],"0")

    def test_negative_price_is_rejected(self):
        out=resolve_external_market_estimate(E,[c("justtcg",market_price=-1)])
        self.assertFalse(out["available"])

    def test_number_total_suffix_does_not_break_exact_card_number(self):
        checked=validate_candidate(E,c("justtcg",card_number="113/236"))
        self.assertTrue(checked["accepted"])


if __name__=="__main__":
    unittest.main(verbosity=2)
