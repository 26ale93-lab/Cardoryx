#!/usr/bin/env python3
"""Cardmarket identity regression audit for Cardoryx.

The script only writes its JSON diagnostic report. It verifies the exact
production overrides already present in index.html, then joins the pinned
TCGdex database snapshot, the live TCGdex pricing view, and Cardmarket's
official Product Catalogue and Price Guide.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
VARIANT_REPORT = ROOT / "artifacts" / "variant_finish_audit_report.json"
PLAY_INDEX = ROOT / "data" / "cardmarket_play_index.json"
OUT = ROOT / "artifacts" / "card_identity_cardmarket_audit_report.json"
API = "https://api.tcgdex.net/v2/en/cards"
CM_BASE = "https://downloads.s3.cardmarket.com/productCatalog"

# Exact Cardmarket catalogue identities and current Price Guide values prove
# the base/conflicting product pairs. The Surging Sparks cases are V1/V2
# Horizons inversions; Piplup is CEC54 base versus CEC239 Character Rare.
CONFIRMED_BASE_PRODUCT_CONFLICTS = {
    "sv08-029": {"base": 794286, "alternate": 794946, "stamp": "horizons", "cardmarketCode": "SSP029"},
    "sv08-050": {"base": 794316, "alternate": 794947, "stamp": "horizons", "cardmarketCode": "SSP050"},
    "sv08-161": {"base": 794534, "alternate": 794948, "stamp": "horizons", "cardmarketCode": "SSP161"},
    "sm12-54": {"base": 407919, "alternate": 398504, "stamp": "character-rare", "cardmarketCode": "CEC54"},
    "ecard1-66": {"base": 274941, "alternate": 274904, "stamp": "wrong-holo-number", "cardmarketCode": "EX66"},
    "pl3-7": {"base": 278698, "alternate": 278689, "stamp": "wrong-card-identity", "cardmarketCode": "SV7"},
    "pl3-70": {"base": 278761, "alternate": 882910, "stamp": "special-v2-source-conflict", "cardmarketCode": "SV70"},
    "sv10.5b-027": {"base": 835953, "alternate": 835994, "stamp": "wrong-card-identity", "cardmarketCode": "BLK027"},
    "sv10.5b-014": {"base": 835929, "alternate": 835069, "stamp": "unverified-top-level-product", "cardmarketCode": "BLK014"},
    "sv10.5b-065": {"base": 836043, "alternate": 836009, "stamp": "wrong-card-identity", "cardmarketCode": "BLK065"},
    "swsh11-201": {"base": 674207, "alternate": 670816, "stamp": "wrong-card-identity", "cardmarketCode": "LOR201"},
    "sv03-062": {"base": 725142, "alternate": 727118, "stamp": "pre-release-top-level", "cardmarketCode": "OBF062"},
    "sv03-056": {"base": 725136, "alternate": 781857, "stamp": "cosmos-reprint-top-level", "cardmarketCode": "OBF056"},
    "ex4-6": {"base": 275983, "alternate": 275783, "stamp": "wrong-card-identity", "cardmarketCode": "MA6"},
    "ex4-7": {"base": 275984, "alternate": 275784, "stamp": "wrong-card-identity", "cardmarketCode": "MA7"},
    "ex4-89": {"base": 276066, "alternate": 275866, "stamp": "wrong-card-identity", "cardmarketCode": "MA89"},
    "ex4-94": {"base": 276071, "alternate": 275871, "stamp": "wrong-card-identity", "cardmarketCode": "MA94"},
    "ex4-95": {"base": 276072, "alternate": 275872, "stamp": "wrong-card-identity", "cardmarketCode": "MA95"},
    "ex4-19": {"base": 275996, "alternate": 275796, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-19"},
    "ex4-23": {"base": 276000, "alternate": 275800, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-23"},
    "ex4-64": {"base": 276041, "alternate": 275841, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-64"},
    "ex4-73": {"base": 276050, "alternate": 275850, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-73"},
    "ex4-78": {"base": 276055, "alternate": 275855, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-78"},
    "ex4-80": {"base": 276057, "alternate": 275857, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-80"},
    "ex4-82": {"base": 276059, "alternate": 275859, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-82"},
    "ex4-85": {"base": 276062, "alternate": 275862, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-85"},
    "ex4-87": {"base": 276064, "alternate": 275864, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-87"},
    "ex4-1": {"base": 275978, "alternate": 275778, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-1"},
    "ex4-3": {"base": 275980, "alternate": 275780, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-3"},
    "ex4-9": {"base": 275986, "alternate": 275786, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-9"},
    "ex4-12": {"base": 275989, "alternate": 275789, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-12"},
    "ex4-13": {"base": 275990, "alternate": 275790, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-13"},
    "ex4-17": {"base": 275994, "alternate": 275794, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-17"},
    "ex4-28": {"base": 276005, "alternate": 275805, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-28"},
    "ex4-39": {"base": 276016, "alternate": 275816, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-39"},
    "ex4-40": {"base": 276017, "alternate": 275817, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-40"},
    "ex4-41": {"base": 276018, "alternate": 275818, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-41"},
    "ex4-42": {"base": 276019, "alternate": 275819, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-42"},
    "ex4-43": {"base": 276020, "alternate": 275820, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-43"},
    "ex4-44": {"base": 276021, "alternate": 275821, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-44"},
    "ex4-45": {"base": 276022, "alternate": 275822, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-45"},
    "ex4-46": {"base": 276023, "alternate": 275823, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-46"},
    "ex4-49": {"base": 276026, "alternate": 275826, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-49"},
    "ex4-69": {"base": 276046, "alternate": 275846, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-69"},
    "ex4-70": {"base": 276047, "alternate": 275847, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-70"},
    "ex4-71": {"base": 276048, "alternate": 275848, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-71"},
    "ex4-72": {"base": 276049, "alternate": 275849, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-72"},
    "ex4-74": {"base": 276051, "alternate": 275851, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-74"},
    "ex4-75": {"base": 276052, "alternate": 275852, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-75"},
    "ex4-76": {"base": 276053, "alternate": 275853, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-76"},
    "ex4-77": {"base": 276054, "alternate": 275854, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-77"},
    "ex4-79": {"base": 276056, "alternate": 275856, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-79"},
    "ex4-81": {"base": 276058, "alternate": 275858, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-81"},
    "ex4-83": {"base": 276060, "alternate": 275860, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-83"},
    "ex4-84": {"base": 276061, "alternate": 275861, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-84"},
    "ex4-86": {"base": 276063, "alternate": 275863, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-86"},
    "ex4-88": {"base": 276065, "alternate": 275865, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-88"},
    "ex8-17": {"base": 276420, "alternate": 276419, "stamp": "wrong-card-identity", "cardmarketCode": "DX17"},
    "ex8-18": {"base": 276421, "alternate": 276419, "stamp": "wrong-card-identity", "cardmarketCode": "DX18"}
}
VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS = {
    "sv05-041": {"setId": "sv05", "localId": "041", "name": "Feraligatr", "expansion": 5589, "metacard": 430014, "normal": 761970, "holo": 760671, "reverse": 760671},
    "sv08-065": {"setId": "sv08", "localId": "065", "name": "Tapu Koko", "expansion": 5879, "metacard": 441182, "normal": 799718, "holo": 794346, "reverse": 794346},
}
VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS = {
    "ex5-98": {"setId":"ex5","localId":"98","name":"Regirock ex","primary":276172,"primaryType":"holo","primaryFoil":"cracked-ice","primaryStamp":[],"alternate":869536,"alternateType":"normal","alternateFoil":"","alternateStamp":["jason-klaczynski"]},
    "swshp-SWSH039": {"setId":"swshp","localId":"SWSH039","name":"Pikachu","primary":491189,"primaryType":"holo","primaryFoil":"cosmos","primaryStamp":[],"alternate":549406,"alternateType":"holo","alternateFoil":"","alternateStamp":["25th-celebration"]},
}
MFB_POKEBALL_EXACT_ROWS = {
    "mfb-1": {"setId":"mfb","localId":"1","name":"Bulbasaur","deckToken":"bulbasaur","base":741976,"pokeball":741975},
    "mfb-8": {"setId":"mfb","localId":"8","name":"Grass Energy","deckToken":"bulbasaur","base":741986,"pokeball":741985},
    "mfb-16": {"setId":"mfb","localId":"16","name":"Fire Energy","deckToken":"charmander","base":741998,"pokeball":741997},
    "mfb-17": {"setId":"mfb","localId":"17","name":"Pikachu","deckToken":"pikachu","base":742000,"pokeball":741999},
    "mfb-24": {"setId":"mfb","localId":"24","name":"Lightning Energy","deckToken":"pikachu","base":742010,"pokeball":742009},
    "mfb-25": {"setId":"mfb","localId":"25","name":"Squirtle","deckToken":"squirtle","base":742012,"pokeball":742011},
}
VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS = {
    "swshp-SWSH296": {"setId":"swshp","localId":"SWSH296","name":"Champions Festival","stamp":"worlds-2022","productId":671798,"staffProductId":672087},
    "svp-045": {"setId":"svp","localId":"045","name":"Paradise Resort","stamp":"worlds-2023","productId":726924,"staffProductId":727542},
    "svp-150": {"setId":"svp","localId":"150","name":"Paradise Resort","stamp":"worlds-2024","productId":783445,"staffProductId":783446},
}
VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS = {
    "svp-067": {"setId": "svp", "localId": "067", "name": "Roaring Moon ex", "expansion": 5241, "metacard": 426438, "standard": 740407, "jumbo": 740408, "stamp": []},
    "swshp-SWSH055": {"setId": "swshp", "localId": "SWSH055", "name": "Hatterene V", "expansion": 2916, "metacard": 322125, "standard": 510180, "jumbo": 510175, "stamp": []},
    "swshp-SWSH132": {"setId": "swshp", "localId": "SWSH132", "name": "Dragapult", "expansion": 2916, "metacard": 345894, "standard": 576731, "jumbo": 576905, "stamp": ["25th-celebration"]},
    "swshp-SWSH133": {"setId": "swshp", "localId": "SWSH133", "name": "Lance's Charizard V", "expansion": 2916, "metacard": 345895, "standard": 576732, "jumbo": 576906, "stamp": ["25th-celebration"]},
    "swshp-SWSH134": {"setId": "swshp", "localId": "SWSH134", "name": "Dark Sylveon V", "expansion": 2916, "metacard": 345896, "standard": 576733, "jumbo": 576907, "stamp": ["25th-celebration"]},
    "swshp-SWSH136": {"setId": "swshp", "localId": "SWSH136", "name": "Mimikyu", "expansion": 2916, "metacard": 345898, "standard": 576735, "jumbo": 576908, "stamp": ["25th-celebration"]},
    "swshp-SWSH137": {"setId": "swshp", "localId": "SWSH137", "name": "Light Toxtricity", "expansion": 2916, "metacard": 345899, "standard": 576736, "jumbo": 576909, "stamp": ["25th-celebration"]},
    "swshp-SWSH138": {"setId": "swshp", "localId": "SWSH138", "name": "Hydreigon C", "expansion": 2916, "metacard": 345900, "standard": 576737, "jumbo": 576910, "stamp": ["25th-celebration"]},
}
MCDONALDS_2021_EXACT_PAIRS = {
    "2021swsh-1": {"localId": "1", "name": "Bulbasaur", "normal": 538778, "holo": 538783},
    "2021swsh-2": {"localId": "2", "name": "Chikorita", "normal": 538788, "holo": 538793},
    "2021swsh-3": {"localId": "3", "name": "Treecko", "normal": 538798, "holo": 538803},
    "2021swsh-4": {"localId": "4", "name": "Turtwig", "normal": 538808, "holo": 538813},
    "2021swsh-5": {"localId": "5", "name": "Snivy", "normal": 538818, "holo": 538823},
    "2021swsh-6": {"localId": "6", "name": "Chespin", "normal": 538828, "holo": 538833},
    "2021swsh-7": {"localId": "7", "name": "Rowlet", "normal": 538838, "holo": 538843},
    "2021swsh-8": {"localId": "8", "name": "Grookey", "normal": 538848, "holo": 538853},
    "2021swsh-9": {"localId": "9", "name": "Charmander", "normal": 538858, "holo": 538863},
    "2021swsh-10": {"localId": "10", "name": "Cyndaquil", "normal": 538868, "holo": 538873},
    "2021swsh-11": {"localId": "11", "name": "Torchic", "normal": 538878, "holo": 538883},
    "2021swsh-12": {"localId": "12", "name": "Chimchar", "normal": 538888, "holo": 538893},
    "2021swsh-13": {"localId": "13", "name": "Tepig", "normal": 538898, "holo": 538903},
    "2021swsh-14": {"localId": "14", "name": "Fennekin", "normal": 538908, "holo": 538913},
    "2021swsh-15": {"localId": "15", "name": "Litten", "normal": 538918, "holo": 538923},
    "2021swsh-16": {"localId": "16", "name": "Scorbunny", "normal": 538928, "holo": 538933},
    "2021swsh-17": {"localId": "17", "name": "Squirtle", "normal": 538938, "holo": 538943},
    "2021swsh-18": {"localId": "18", "name": "Totodile", "normal": 538948, "holo": 538953},
    "2021swsh-19": {"localId": "19", "name": "Mudkip", "normal": 538958, "holo": 538963},
    "2021swsh-20": {"localId": "20", "name": "Piplup", "normal": 538968, "holo": 538973},
    "2021swsh-21": {"localId": "21", "name": "Oshawott", "normal": 538978, "holo": 538983},
    "2021swsh-22": {"localId": "22", "name": "Froakie", "normal": 538988, "holo": 538993},
    "2021swsh-23": {"localId": "23", "name": "Popplio", "normal": 538998, "holo": 539003},
    "2021swsh-24": {"localId": "24", "name": "Sobble", "normal": 539008, "holo": 539013},
    "2021swsh-25": {"localId": "25", "name": "Pikachu", "normal": 539018, "holo": 539023},
}
PROTECTED_REVERSE = {"pl2-102", "pl3-26", "pl3-5", "pl3-59", "pl3-83", "sv10.5b-013"}
EX8_VERIFIED_SHARED_PRODUCT_OWNERS = {
    "ex8-16": {"productId": 276419, "blockedTcgdexIds": {"ex8-17", "ex8-18", "ex8-98", "ex8-99"}},
    "ex8-22": {"productId": 276425, "blockedTcgdexIds": {"ex8-107"}},
}
EXPECTED_BASE_OVERRIDES = {
    "sv08-029": {"setId": "sv08", "localId": "029", "conflictingProduct": 794946, "baseProduct": 794286},
    "sv08-050": {"setId": "sv08", "localId": "050", "conflictingProduct": 794947, "baseProduct": 794316},
    "sv08-161": {"setId": "sv08", "localId": "161", "conflictingProduct": 794948, "baseProduct": 794534},
    "sm12-54": {"setId": "sm12", "localId": "054", "conflictingProduct": 398504, "baseProduct": 407919},
    "ecard1-66": {"setId": "ecard1", "localId": "066", "conflictingProduct": 274904, "baseProduct": 274941},
    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},
    "pl3-70": {"setId": "pl3", "localId": "070", "conflictingProduct": 882910, "baseProduct": 278761},
    "sv10.5b-027": {"setId": "sv10.5b", "localId": "027", "conflictingProduct": 835994, "baseProduct": 835953},
    "sv10.5b-014": {"setId": "sv10.5b", "localId": "014", "conflictingProduct": 835069, "baseProduct": 835929},
    "sv10.5b-065": {"setId": "sv10.5b", "localId": "065", "conflictingProduct": 836009, "baseProduct": 836043},
    "swsh11-201": {"setId": "swsh11", "localId": "201", "conflictingProduct": 670816, "baseProduct": 674207},
    "sv03-062": {"setId": "sv03", "localId": "062", "conflictingProduct": 727118, "baseProduct": 725142},
    "sv03-056": {"setId": "sv03", "localId": "056", "conflictingProduct": 781857, "baseProduct": 725136},
    "ex5-29": {"setId": "ex5", "localId": "029", "conflictingProduct": 280585, "baseProduct": 276103},
    "ex4-6": {"setId": "ex4", "localId": "006", "conflictingProduct": 275783, "baseProduct": 275983},
    "ex4-7": {"setId": "ex4", "localId": "007", "conflictingProduct": 275784, "baseProduct": 275984},
    "ex4-89": {"setId": "ex4", "localId": "089", "conflictingProduct": 275866, "baseProduct": 276066},
    "ex4-94": {"setId": "ex4", "localId": "094", "conflictingProduct": 275871, "baseProduct": 276071},
    "ex4-95": {"setId": "ex4", "localId": "095", "conflictingProduct": 275872, "baseProduct": 276072},
    "ex4-19": {"setId": "ex4", "localId": "019", "conflictingProduct": 275796, "baseProduct": 275996},
    "ex4-23": {"setId": "ex4", "localId": "023", "conflictingProduct": 275800, "baseProduct": 276000},
    "ex4-64": {"setId": "ex4", "localId": "064", "conflictingProduct": 275841, "baseProduct": 276041},
    "ex4-73": {"setId": "ex4", "localId": "073", "conflictingProduct": 275850, "baseProduct": 276050},
    "ex4-78": {"setId": "ex4", "localId": "078", "conflictingProduct": 275855, "baseProduct": 276055},
    "ex4-80": {"setId": "ex4", "localId": "080", "conflictingProduct": 275857, "baseProduct": 276057},
    "ex4-82": {"setId": "ex4", "localId": "082", "conflictingProduct": 275859, "baseProduct": 276059},
    "ex4-85": {"setId": "ex4", "localId": "085", "conflictingProduct": 275862, "baseProduct": 276062},
    "ex4-87": {"setId": "ex4", "localId": "087", "conflictingProduct": 275864, "baseProduct": 276064},
    "ex4-1": {"setId": "ex4", "localId": "001", "conflictingProduct": 275778, "baseProduct": 275978},
    "ex4-3": {"setId": "ex4", "localId": "003", "conflictingProduct": 275780, "baseProduct": 275980},
    "ex4-9": {"setId": "ex4", "localId": "009", "conflictingProduct": 275786, "baseProduct": 275986},
    "ex4-12": {"setId": "ex4", "localId": "012", "conflictingProduct": 275789, "baseProduct": 275989},
    "ex4-13": {"setId": "ex4", "localId": "013", "conflictingProduct": 275790, "baseProduct": 275990},
    "ex4-17": {"setId": "ex4", "localId": "017", "conflictingProduct": 275794, "baseProduct": 275994},
    "ex4-28": {"setId": "ex4", "localId": "028", "conflictingProduct": 275805, "baseProduct": 276005},
    "ex4-39": {"setId": "ex4", "localId": "039", "conflictingProduct": 275816, "baseProduct": 276016},
    "ex4-40": {"setId": "ex4", "localId": "040", "conflictingProduct": 275817, "baseProduct": 276017},
    "ex4-41": {"setId": "ex4", "localId": "041", "conflictingProduct": 275818, "baseProduct": 276018},
    "ex4-42": {"setId": "ex4", "localId": "042", "conflictingProduct": 275819, "baseProduct": 276019},
    "ex4-43": {"setId": "ex4", "localId": "043", "conflictingProduct": 275820, "baseProduct": 276020},
    "ex4-44": {"setId": "ex4", "localId": "044", "conflictingProduct": 275821, "baseProduct": 276021},
    "ex4-45": {"setId": "ex4", "localId": "045", "conflictingProduct": 275822, "baseProduct": 276022},
    "ex4-46": {"setId": "ex4", "localId": "046", "conflictingProduct": 275823, "baseProduct": 276023},
    "ex4-49": {"setId": "ex4", "localId": "049", "conflictingProduct": 275826, "baseProduct": 276026},
    "ex4-69": {"setId": "ex4", "localId": "069", "conflictingProduct": 275846, "baseProduct": 276046},
    "ex4-70": {"setId": "ex4", "localId": "070", "conflictingProduct": 275847, "baseProduct": 276047},
    "ex4-71": {"setId": "ex4", "localId": "071", "conflictingProduct": 275848, "baseProduct": 276048},
    "ex4-72": {"setId": "ex4", "localId": "072", "conflictingProduct": 275849, "baseProduct": 276049},
    "ex4-74": {"setId": "ex4", "localId": "074", "conflictingProduct": 275851, "baseProduct": 276051},
    "ex4-75": {"setId": "ex4", "localId": "075", "conflictingProduct": 275852, "baseProduct": 276052},
    "ex4-76": {"setId": "ex4", "localId": "076", "conflictingProduct": 275853, "baseProduct": 276053},
    "ex4-77": {"setId": "ex4", "localId": "077", "conflictingProduct": 275854, "baseProduct": 276054},
    "ex4-79": {"setId": "ex4", "localId": "079", "conflictingProduct": 275856, "baseProduct": 276056},
    "ex4-81": {"setId": "ex4", "localId": "081", "conflictingProduct": 275858, "baseProduct": 276058},
    "ex4-83": {"setId": "ex4", "localId": "083", "conflictingProduct": 275860, "baseProduct": 276060},
    "ex4-84": {"setId": "ex4", "localId": "084", "conflictingProduct": 275861, "baseProduct": 276061},
    "ex4-86": {"setId": "ex4", "localId": "086", "conflictingProduct": 275863, "baseProduct": 276063},
    "ex4-88": {"setId": "ex4", "localId": "088", "conflictingProduct": 275865, "baseProduct": 276065},
    "ex8-17": {"setId": "ex8", "localId": "017", "conflictingProduct": 276419, "baseProduct": 276420},
    "ex8-18": {"setId": "ex8", "localId": "018", "conflictingProduct": 276419, "baseProduct": 276421}
}

# P1 mass batch 2: every tuple is an independently verified exact catalogue
# identity (set/localId/current wrong product/correct product). No arithmetic
# relationship between Cardmarket IDs is used by either audit or production.
BATCH2_BASE_OVERRIDE_ROWS = {
    "gym1-27": ("gym1", "27", 274142, 274163), "gym1-62": ("gym1", "62", 274171, 274198),
    "gym1-46": ("gym1", "46", 274152, 274182), "gym1-49": ("gym1", "49", 274152, 274185),
    "gym1-57": ("gym1", "57", 274154, 274193), "gym1-66": ("gym1", "66", 274151, 274202),
    "gym1-68": ("gym1", "68", 274151, 274204), "gym1-69": ("gym1", "69", 274151, 274205),
    "gym1-70": ("gym1", "70", 274151, 274206), "gym1-72": ("gym1", "72", 274151, 274208),
    "gym1-74": ("gym1", "74", 274151, 274210), "gym1-76": ("gym1", "76", 274152, 274212),
    "gym1-77": ("gym1", "77", 274152, 274213), "gym1-78": ("gym1", "78", 274152, 274214),
    "gym1-80": ("gym1", "80", 274153, 274216), "gym1-83": ("gym1", "83", 274153, 274219),
    "gym1-85": ("gym1", "85", 274154, 274221), "gym2-74": ("gym2", "74", 274286, 274342),
    "gym2-79": ("gym2", "79", 274287, 274347), "gym2-80": ("gym2", "80", 274287, 274348),
    "gym2-94": ("gym2", "94", 274288, 274362), "gym2-97": ("gym2", "97", 274288, 274365),
    "neo1-11": ("neo1", "11", 274410, 274411), "neo1-18": ("neo1", "18", 274417, 274418),
    "neo1-29": ("neo1", "29", 274428, 274429), "neo1-32": ("neo1", "32", 274431, 274432),
    "neo1-5": ("neo1", "5", 274404, 274405), "neo1-47": ("neo1", "47", 274446, 274447),
    "neo1-54": ("neo1", "54", 274453, 274454), "neo1-57": ("neo1", "57", 274456, 274457),
    "neo1-81": ("neo1", "81", 274480, 274481), "neo2-20": ("neo2", "20", 274512, 274531),
    "neo2-32": ("neo2", "32", 274524, 274543), "neo2-39": ("neo2", "39", 274516, 274550),
    "neo3-16": ("neo3", "16", 274589, 274602), "neo3-17": ("neo3", "17", 274592, 274603),
    "neo3-18": ("neo3", "18", 274593, 274604), "neo3-22": ("neo3", "22", 274599, 274608),
    "neo3-27": ("neo3", "27", 274600, 274613), "hgss1-108": ("hgss1", "108", 278992, 279080),
    "hgss1-110": ("hgss1", "110", 279004, 279082), "hgss1-123": ("hgss1", "123", 278976, 279095),
    "pl2-1": ("pl2", "1", 278570, 278575), "pl2-2": ("pl2", "2", 278569, 278576),
    "pl2-3": ("pl2", "3", 278572, 278577), "pl2-4": ("pl2", "4", 278571, 278578),
    "pl2-6": ("pl2", "6", 278574, 278580),
    "swshp-swsh055": ("swshp", "SWSH055", 510175, 510180),
}
EXPECTED_BASE_OVERRIDES.update({
    card_id: {"setId": set_id, "localId": local_id, "conflictingProduct": wrong, "baseProduct": correct}
    for card_id, (set_id, local_id, wrong, correct) in BATCH2_BASE_OVERRIDE_ROWS.items()
})
CONFIRMED_BASE_PRODUCT_CONFLICTS.update({
    card_id: {"base": correct, "alternate": wrong, "stamp": "exact-wrong-physical-product", "cardmarketCode": local_id}
    for card_id, (_, local_id, wrong, correct) in BATCH2_BASE_OVERRIDE_ROWS.items()
})

LEGACY_CHECKLIST_PRODUCTS = {
    'gym1-15': ('gym1', '15', 'Brock', 'Holo', 274151, 274151, 1529, 'gym1-98'),
    'gym1-98': ('gym1', '98', 'Brock', 'Normal', 274234, 274151, 1529, 'gym1-15'),
    'gym1-16': ('gym1', '16', 'Erika', 'Holo', 274152, 274152, 1529, 'gym1-100'),
    'gym1-100': ('gym1', '100', 'Erika', 'Normal', 274236, 274152, 1529, 'gym1-16'),
    'gym1-17': ('gym1', '17', 'Lt. Surge', 'Holo', 274153, 274153, 1529, 'gym1-101'),
    'gym1-101': ('gym1', '101', 'Lt. Surge', 'Normal', 274237, 274153, 1529, 'gym1-17'),
    'gym1-18': ('gym1', '18', 'Misty', 'Holo', 274154, 274154, 1529, 'gym1-102'),
    'gym1-102': ('gym1', '102', 'Misty', 'Normal', 274238, 274154, 1529, 'gym1-18'),
    'gym2-17': ('gym2', '17', 'Blaine', 'Holo', 274285, 274285, 1530, 'gym2-100'),
    'gym2-100': ('gym2', '100', 'Blaine', 'Normal', 274368, 274285, 1530, 'gym2-17'),
    'gym2-18': ('gym2', '18', 'Giovanni', 'Holo', 274286, 274286, 1530, 'gym2-104'),
    'gym2-104': ('gym2', '104', 'Giovanni', 'Normal', 274372, 274286, 1530, 'gym2-18'),
    'gym2-19': ('gym2', '19', 'Koga', 'Holo', 274287, 274287, 1530, 'gym2-106'),
    'gym2-106': ('gym2', '106', 'Koga', 'Normal', 274374, 274287, 1530, 'gym2-19'),
    'gym2-20': ('gym2', '20', 'Sabrina', 'Holo', 274288, 274288, 1530, 'gym2-110'),
    'gym2-110': ('gym2', '110', 'Sabrina', 'Normal', 274378, 274288, 1530, 'gym2-20'),
    'neo2-2': ('neo2', '2', 'Forretress', 'Holo', 274513, 274513, 1532, 'neo2-21'),
    'neo2-21': ('neo2', '21', 'Forretress', 'Normal', 274532, 274513, 1532, 'neo2-2'),
    'neo2-3': ('neo2', '3', 'Hitmontop', 'Holo', 274514, 274514, 1532, 'neo2-22'),
    'neo2-22': ('neo2', '22', 'Hitmontop', 'Normal', 274533, 274514, 1532, 'neo2-3'),
    'neo2-4': ('neo2', '4', 'Houndoom', 'Holo', 274515, 274515, 1532, 'neo2-23'),
    'neo2-23': ('neo2', '23', 'Houndoom', 'Normal', 274534, 274515, 1532, 'neo2-4'),
    'neo2-5': ('neo2', '5', 'Houndour', 'Holo', 274516, 274516, 1532, 'neo2-24'),
    'neo2-24': ('neo2', '24', 'Houndour', 'Normal', 274535, 274516, 1532, 'neo2-5'),
    'neo2-6': ('neo2', '6', 'Kabutops', 'Holo', 274517, 274517, 1532, 'neo2-25'),
    'neo2-25': ('neo2', '25', 'Kabutops', 'Normal', 274536, 274517, 1532, 'neo2-6'),
    'neo2-7': ('neo2', '7', 'Magnemite', 'Holo', 274518, 274518, 1532, 'neo2-26'),
    'neo2-26': ('neo2', '26', 'Magnemite', 'Normal', 274537, 274518, 1532, 'neo2-7'),
    'neo2-8': ('neo2', '8', 'Politoed', 'Holo', 274519, 274519, 1532, 'neo2-27'),
    'neo2-27': ('neo2', '27', 'Politoed', 'Normal', 274538, 274519, 1532, 'neo2-8'),
    'neo2-9': ('neo2', '9', 'Poliwrath', 'Holo', 274520, 274520, 1532, 'neo2-28'),
    'neo2-28': ('neo2', '28', 'Poliwrath', 'Normal', 274539, 274520, 1532, 'neo2-9'),
    'neo2-10': ('neo2', '10', 'Scizor', 'Holo', 274521, 274521, 1532, 'neo2-29'),
    'neo2-29': ('neo2', '29', 'Scizor', 'Normal', 274540, 274521, 1532, 'neo2-10'),
    'neo2-11': ('neo2', '11', 'Smeargle', 'Holo', 274522, 274522, 1532, 'neo2-30'),
    'neo2-30': ('neo2', '30', 'Smeargle', 'Normal', 274541, 274522, 1532, 'neo2-11'),
    'neo2-12': ('neo2', '12', 'Tyranitar', 'Holo', 274523, 274523, 1532, 'neo2-31'),
    'neo2-31': ('neo2', '31', 'Tyranitar', 'Normal', 274542, 274523, 1532, 'neo2-12'),
    'neo2-14': ('neo2', '14', 'Unown [A]', 'Holo', 274525, 274525, 1532, 'neo2-33'),
    'neo2-33': ('neo2', '33', 'Unown [A]', 'Normal', 274544, 274525, 1532, 'neo2-14'),
    'neo2-15': ('neo2', '15', 'Ursaring', 'Holo', 274526, 274526, 1532, 'neo2-34'),
    'neo2-34': ('neo2', '34', 'Ursaring', 'Normal', 274545, 274526, 1532, 'neo2-15'),
    'neo2-16': ('neo2', '16', 'Wobbuffet', 'Holo', 274527, 274527, 1532, 'neo2-35'),
    'neo2-35': ('neo2', '35', 'Wobbuffet', 'Normal', 274546, 274527, 1532, 'neo2-16'),
    'neo2-17': ('neo2', '17', 'Yanma', 'Holo', 274528, 274528, 1532, 'neo2-36'),
    'neo2-36': ('neo2', '36', 'Yanma', 'Normal', 274547, 274528, 1532, 'neo2-17'),
    'base3-1': ('base3', '1', 'Aerodactyl', 'Holo', 273862, 273862, 1526, 'base3-16'),
    'base3-16': ('base3', '16', 'Aerodactyl', 'Normal', 273877, 273862, 1526, 'base3-1'),
    'base3-2': ('base3', '2', 'Articuno', 'Holo', 273863, 273863, 1526, 'base3-17'),
    'base3-17': ('base3', '17', 'Articuno', 'Normal', 273878, 273863, 1526, 'base3-2'),
    'base3-3': ('base3', '3', 'Ditto', 'Holo', 273864, 273864, 1526, 'base3-18'),
    'base3-18': ('base3', '18', 'Ditto', 'Normal', 273879, 273864, 1526, 'base3-3'),
    'base3-4': ('base3', '4', 'Dragonite', 'Holo', 273865, 273865, 1526, 'base3-19'),
    'base3-19': ('base3', '19', 'Dragonite', 'Normal', 273880, 273865, 1526, 'base3-4'),
    'base3-5': ('base3', '5', 'Gengar', 'Holo', 273866, 273866, 1526, 'base3-20'),
    'base3-20': ('base3', '20', 'Gengar', 'Normal', 273881, 273866, 1526, 'base3-5'),
    'base3-6': ('base3', '6', 'Haunter', 'Holo', 273867, 273867, 1526, 'base3-21'),
    'base3-21': ('base3', '21', 'Haunter', 'Normal', 273882, 273867, 1526, 'base3-6'),
    'base3-7': ('base3', '7', 'Hitmonlee', 'Holo', 273868, 273868, 1526, 'base3-22'),
    'base3-22': ('base3', '22', 'Hitmonlee', 'Normal', 273883, 273868, 1526, 'base3-7'),
    'base3-8': ('base3', '8', 'Hypno', 'Holo', 273869, 273869, 1526, 'base3-23'),
    'base3-23': ('base3', '23', 'Hypno', 'Normal', 273884, 273869, 1526, 'base3-8'),
    'base3-9': ('base3', '9', 'Kabutops', 'Holo', 273870, 273870, 1526, 'base3-24'),
    'base3-24': ('base3', '24', 'Kabutops', 'Normal', 273885, 273870, 1526, 'base3-9'),
    'base3-10': ('base3', '10', 'Lapras', 'Holo', 273871, 273871, 1526, 'base3-25'),
    'base3-25': ('base3', '25', 'Lapras', 'Normal', 273886, 273871, 1526, 'base3-10'),
    'base3-11': ('base3', '11', 'Magneton', 'Holo', 273872, 273872, 1526, 'base3-26'),
    'base3-26': ('base3', '26', 'Magneton', 'Normal', 273887, 273872, 1526, 'base3-11'),
    'base3-12': ('base3', '12', 'Moltres', 'Holo', 273873, 273873, 1526, 'base3-27'),
    'base3-27': ('base3', '27', 'Moltres', 'Normal', 273888, 273873, 1526, 'base3-12'),
    'base3-13': ('base3', '13', 'Muk', 'Holo', 273874, 273874, 1526, 'base3-28'),
    'base3-28': ('base3', '28', 'Muk', 'Normal', 273889, 273874, 1526, 'base3-13'),
    'base3-14': ('base3', '14', 'Raichu', 'Holo', 273875, 273875, 1526, 'base3-29'),
    'base3-29': ('base3', '29', 'Raichu', 'Normal', 273890, 273875, 1526, 'base3-14'),
    'base3-15': ('base3', '15', 'Zapdos', 'Holo', 273876, 273876, 1526, 'base3-30'),
    'base3-30': ('base3', '30', 'Zapdos', 'Normal', 273891, 273876, 1526, 'base3-15'),
    'base2-1': ('base2', '1', 'Clefable', 'Holo', 273798, 273798, 1525, 'base2-17'),
    'base2-17': ('base2', '17', 'Clefable', 'Normal', 273814, 273798, 1525, 'base2-1'),
    'base2-2': ('base2', '2', 'Electrode', 'Holo', 273799, 273799, 1525, 'base2-18'),
    'base2-18': ('base2', '18', 'Electrode', 'Normal', 273815, 273799, 1525, 'base2-2'),
    'base2-3': ('base2', '3', 'Flareon', 'Holo', 273800, 273800, 1525, 'base2-19'),
    'base2-19': ('base2', '19', 'Flareon', 'Normal', 273816, 273800, 1525, 'base2-3'),
    'base2-4': ('base2', '4', 'Jolteon', 'Holo', 273801, 273801, 1525, 'base2-20'),
    'base2-20': ('base2', '20', 'Jolteon', 'Normal', 273817, 273801, 1525, 'base2-4'),
    'base2-5': ('base2', '5', 'Kangaskhan', 'Holo', 273802, 273802, 1525, 'base2-21'),
    'base2-21': ('base2', '21', 'Kangaskhan', 'Normal', 273818, 273802, 1525, 'base2-5'),
    'base2-6': ('base2', '6', 'Mr. Mime', 'Holo', 273803, 273803, 1525, 'base2-22'),
    'base2-22': ('base2', '22', 'Mr. Mime', 'Normal', 273819, 273803, 1525, 'base2-6'),
    'base2-7': ('base2', '7', 'Nidoqueen', 'Holo', 273804, 273804, 1525, 'base2-23'),
    'base2-23': ('base2', '23', 'Nidoqueen', 'Normal', 273820, 273804, 1525, 'base2-7'),
    'base2-8': ('base2', '8', 'Pidgeot', 'Holo', 273805, 273805, 1525, 'base2-24'),
    'base2-24': ('base2', '24', 'Pidgeot', 'Normal', 273821, 273805, 1525, 'base2-8'),
    'base2-9': ('base2', '9', 'Pinsir', 'Holo', 273806, 273806, 1525, 'base2-25'),
    'base2-25': ('base2', '25', 'Pinsir', 'Normal', 273822, 273806, 1525, 'base2-9'),
    'base2-10': ('base2', '10', 'Scyther', 'Holo', 273807, 273807, 1525, 'base2-26'),
    'base2-26': ('base2', '26', 'Scyther', 'Normal', 273823, 273807, 1525, 'base2-10'),
    'base2-11': ('base2', '11', 'Snorlax', 'Holo', 273808, 273808, 1525, 'base2-27'),
    'base2-27': ('base2', '27', 'Snorlax', 'Normal', 273824, 273808, 1525, 'base2-11'),
    'base2-12': ('base2', '12', 'Vaporeon', 'Holo', 273809, 273809, 1525, 'base2-28'),
    'base2-28': ('base2', '28', 'Vaporeon', 'Normal', 273825, 273809, 1525, 'base2-12'),
    'base2-13': ('base2', '13', 'Venomoth', 'Holo', 273810, 273810, 1525, 'base2-29'),
    'base2-29': ('base2', '29', 'Venomoth', 'Normal', 273826, 273810, 1525, 'base2-13'),
    'base2-14': ('base2', '14', 'Victreebel', 'Holo', 273811, 273811, 1525, 'base2-30'),
    'base2-30': ('base2', '30', 'Victreebel', 'Normal', 273827, 273811, 1525, 'base2-14'),
    'base2-15': ('base2', '15', 'Vileplume', 'Holo', 273812, 273812, 1525, 'base2-31'),
    'base2-31': ('base2', '31', 'Vileplume', 'Normal', 273828, 273812, 1525, 'base2-15'),
    'base2-16': ('base2', '16', 'Wigglytuff', 'Holo', 273813, 273813, 1525, 'base2-32'),
    'base2-32': ('base2', '32', 'Wigglytuff', 'Normal', 273829, 273813, 1525, 'base2-16'),
    'base5-1': ('base5', '1', 'Dark Alakazam', 'Holo', 274054, 274054, 1528, 'base5-18'),
    'base5-18': ('base5', '18', 'Dark Alakazam', 'Normal', 274071, 274054, 1528, 'base5-1'),
    'base5-2': ('base5', '2', 'Dark Arbok', 'Holo', 274055, 274055, 1528, 'base5-19'),
    'base5-19': ('base5', '19', 'Dark Arbok', 'Normal', 274072, 274055, 1528, 'base5-2'),
    'base5-3': ('base5', '3', 'Dark Blastoise', 'Holo', 274056, 274056, 1528, 'base5-20'),
    'base5-20': ('base5', '20', 'Dark Blastoise', 'Normal', 274073, 274056, 1528, 'base5-3'),
    'base5-4': ('base5', '4', 'Dark Charizard', 'Holo', 274057, 274057, 1528, 'base5-21'),
    'base5-21': ('base5', '21', 'Dark Charizard', 'Normal', 274074, 274057, 1528, 'base5-4'),
    'base5-5': ('base5', '5', 'Dark Dragonite', 'Holo', 274058, 274058, 1528, 'base5-22'),
    'base5-22': ('base5', '22', 'Dark Dragonite', 'Normal', 274075, 274058, 1528, 'base5-5'),
    'base5-6': ('base5', '6', 'Dark Dugtrio', 'Holo', 274059, 274059, 1528, 'base5-23'),
    'base5-23': ('base5', '23', 'Dark Dugtrio', 'Normal', 274076, 274059, 1528, 'base5-6'),
    'base5-7': ('base5', '7', 'Dark Golbat', 'Holo', 274060, 274060, 1528, 'base5-24'),
    'base5-24': ('base5', '24', 'Dark Golbat', 'Normal', 274077, 274060, 1528, 'base5-7'),
    'base5-8': ('base5', '8', 'Dark Gyarados', 'Holo', 274061, 274061, 1528, 'base5-25'),
    'base5-25': ('base5', '25', 'Dark Gyarados', 'Normal', 274078, 274061, 1528, 'base5-8'),
    'base5-9': ('base5', '9', 'Dark Hypno', 'Holo', 274062, 274062, 1528, 'base5-26'),
    'base5-26': ('base5', '26', 'Dark Hypno', 'Normal', 274079, 274062, 1528, 'base5-9'),
    'base5-10': ('base5', '10', 'Dark Machamp', 'Holo', 274063, 274063, 1528, 'base5-27'),
    'base5-27': ('base5', '27', 'Dark Machamp', 'Normal', 274080, 274063, 1528, 'base5-10'),
    'base5-11': ('base5', '11', 'Dark Magneton', 'Holo', 274064, 274064, 1528, 'base5-28'),
    'base5-28': ('base5', '28', 'Dark Magneton', 'Normal', 274081, 274064, 1528, 'base5-11'),
    'base5-12': ('base5', '12', 'Dark Slowbro', 'Holo', 274065, 274065, 1528, 'base5-29'),
    'base5-29': ('base5', '29', 'Dark Slowbro', 'Normal', 274082, 274065, 1528, 'base5-12'),
    'base5-13': ('base5', '13', 'Dark Vileplume', 'Holo', 274066, 274066, 1528, 'base5-30'),
    'base5-30': ('base5', '30', 'Dark Vileplume', 'Normal', 274083, 274066, 1528, 'base5-13'),
    'base5-14': ('base5', '14', 'Dark Weezing', 'Holo', 274067, 274067, 1528, 'base5-31'),
    'base5-31': ('base5', '31', 'Dark Weezing', 'Normal', 274084, 274067, 1528, 'base5-14'),
    'base5-15': ('base5', '15', 'Here Comes Team Rocket!', 'Holo', 274068, 274068, 1528, 'base5-71'),
    'base5-71': ('base5', '71', 'Here Comes Team Rocket!', 'Normal', 274124, 274068, 1528, 'base5-15'),
    'base5-16': ('base5', '16', "Rocket's Sneak Attack", 'Holo', 274069, 274069, 1528, 'base5-72'),
    'base5-72': ('base5', '72', "Rocket's Sneak Attack", 'Normal', 274125, 274069, 1528, 'base5-16'),
    'base5-17': ('base5', '17', 'Rainbow Energy', 'Holo', 274070, 274070, 1528, 'base5-80'),
    'base5-80': ('base5', '80', 'Rainbow Energy', 'Normal', 274133, 274070, 1528, 'base5-17'),
}

BATCH2_SHARED_PRODUCT_OWNERS = {
    "gym1-6": ("gym1", "6", "Lt. Surge's Electabuzz", 274142),
    "gym1-35": ("gym1", "35", "Blaine's Growlithe", 274171),
    "neo1-10": ("neo1", "10", "Meganium", 274410), "neo1-17": ("neo1", "17", "Typhlosion", 274417),
    "neo1-28": ("neo1", "28", "Bayleef", 274428), "neo1-31": ("neo1", "31", "Croconaw", 274431),
    "neo1-4": ("neo1", "4", "Feraligatr", 274404), "neo1-46": ("neo1", "46", "Quilava", 274446),
    "neo1-53": ("neo1", "53", "Chikorita", 274453), "neo1-56": ("neo1", "56", "Cyndaquil", 274456),
    "neo1-80": ("neo1", "80", "Totodile", 274480), "neo2-1": ("neo2", "1", "Espeon", 274512),
    "neo2-13": ("neo2", "13", "Umbreon", 274524), "neo3-3": ("neo3", "3", "Celebi", 274589),
    "neo3-6": ("neo3", "6", "Entei", 274592), "neo3-7": ("neo3", "7", "Ho-oh", 274593),
    "neo3-13": ("neo3", "13", "Raikou", 274599), "neo3-14": ("neo3", "14", "Suicune", 274600),
    "hgss1-20": ("hgss1", "20", "Feraligatr", 278992), "hgss1-32": ("hgss1", "32", "Typhlosion", 279004),
    "hgss1-4": ("hgss1", "4", "Gyarados", 278976), "pl2-RT1": ("pl2", "RT1", "Fan Rotom", 278570),
    "pl2-RT2": ("pl2", "RT2", "Frost Rotom", 278569), "pl2-RT3": ("pl2", "RT3", "Heat Rotom", 278572),
    "pl2-RT4": ("pl2", "RT4", "Mow Rotom", 278571), "pl2-RT6": ("pl2", "RT6", "Charon's Choice", 278574),
}


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--tcgdex-db", type=Path, default=ROOT.parent / "tcgdex-cards-database")
    parser.add_argument("--products", type=Path)
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "cardoryx-cm-identity-live-cache")
    parser.add_argument("--workers", type=int, default=24)
    return parser.parse_args()


def norm_local(value):
    text = str(value or "").strip().lower()
    return str(int(text)) if text.isdigit() else re.sub(r"[^a-z0-9]+", "", text)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def get_json(url, timeout=90):
    request = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-Cardmarket-Identity-Audit/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def download_if_needed(path, filename):
    if path:
        return path
    destination = Path(tempfile.gettempdir()) / filename
    if not destination.exists():
        section = "productList" if filename.startswith("products_") else "priceGuide"
        request = urllib.request.Request(f"{CM_BASE}/{section}/{filename}", headers={"User-Agent": "Cardoryx-Cardmarket-Identity-Audit/2.0"})
        with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    return destination


def load_snapshot(db_root):
    sys.dont_write_bytecode = True
    path = ROOT / "scripts" / "test_variant_finish_audit.py"
    spec = importlib.util.spec_from_file_location("variant_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_official_database(db_root)


def rows(root, keys):
    if isinstance(root, list):
        return root
    for key in keys:
        value = root.get(key) if isinstance(root, dict) else None
        if isinstance(value, list):
            return value
    return []


def cm_id(row):
    try:
        return int(((row.get("thirdParty") or {}).get("cardmarket")))
    except (TypeError, ValueError):
        return None


def physical_variant(row):
    stamps, foils = row.get("stamp") or [], row.get("foil") or []
    if isinstance(stamps, str):
        stamps = [stamps]
    if isinstance(foils, str):
        foils = [foils]
    return {
        "finish": row.get("type"), "foil": sorted(map(str, foils)), "stamp": sorted(map(str, stamps)),
        "size": row.get("size"), "subtype": row.get("subtype"),
        "language": row.get("language") or row.get("languages"), "variantId": row.get("variantId"),
        "firstEdition": row.get("firstEdition"),
    }


def is_base_row(row):
    return not (row.get("stamp") or row.get("foil") or row.get("firstEdition"))


def card_identity(card):
    set_info, names = card.get("set") or {}, card.get("name") or {}
    set_names = set_info.get("name") or {}
    return {
        "tcgdexId": card.get("id"), "setId": set_info.get("id"),
        "setNameEN": set_names.get("en") if isinstance(set_names, dict) else set_names,
        "setNameIT": set_names.get("it") if isinstance(set_names, dict) else None,
        "localId": card.get("localId"), "normalizedLocalId": norm_local(card.get("localId")),
        "name": names.get("en") if isinstance(names, dict) else names,
        "nameIT": names.get("it") if isinstance(names, dict) else None,
        "rarity": card.get("rarity"), "regulationMark": card.get("regulationMark"),
    }


def product_ids(card):
    return sorted({pid for row in (card.get("variants_detailed") or []) if (pid := cm_id(row))})


def live_card(card_id, cache, retries=3):
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / f"{card_id}.json"
    error_destination = cache / f"{card_id}.error.json"
    if destination.exists():
        try:
            return json.loads(destination.read_text(encoding="utf-8")), None
        except Exception:
            pass
    if error_destination.exists():
        try:
            cached_error = json.loads(error_destination.read_text(encoding="utf-8"))
            return None, cached_error.get("error")
        except Exception:
            pass
    error = None
    for attempt in range(retries):
        try:
            value = get_json(f"{API}/{urllib.parse.quote(card_id)}", timeout=60)
            destination.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            return value, None
        except Exception as exc:
            error = str(exc)
            if "404" in error:
                error_destination.write_text(json.dumps({"error": error}), encoding="utf-8")
                break
            time.sleep(0.4 * (attempt + 1))
    return None, error


def price_compact(row):
    return ({key: row.get(key) for key in ("idProduct", "trend", "avg7", "avg30", "low", "avg") if key in row}
            if row else None)


def descriptor_map(card):
    mapped = defaultdict(list)
    for row in card.get("variants_detailed") or []:
        if (pid := cm_id(row)):
            variant = physical_variant(row)
            if variant not in mapped[pid]:
                mapped[pid].append(variant)
    return dict(mapped)


def extract_js_object(source, name):
    marker = re.search(rf"\bconst\s+{re.escape(name)}\s*=\s*", source)
    if not marker:
        raise AssertionError(f"Missing registry {name}")
    start = source.find("{", marker.end())
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise AssertionError(f"Unclosed registry {name}")
    literal = source[start:end + 2]
    js = f"const value=({literal}); process.stdout.write(JSON.stringify(value));"
    return json.loads(subprocess.check_output(["node", "-e", js], text=True))


def override_matches(rule, card_id, set_id, local_id, current_product):
    return bool(rule and card_id in EXPECTED_BASE_OVERRIDES and
                str(rule.get("setId") or "").lower() == str(set_id or "").lower() and
                norm_local(rule.get("localId")) == norm_local(local_id) and
                int(rule.get("conflictingProduct") or 0) == int(current_product or 0))


def runtime_cardmarket_regression():
    """Execute the production JavaScript resolvers against focused runtime fixtures."""
    mcd2019_rules = extract_js_object(
        INDEX.read_text(encoding="utf-8"),
        "VERIFIED_MCDONALDS_2019_CARDMARKET_PRODUCTS",
    )
    exact_guides = extract_js_object(
        INDEX.read_text(encoding="utf-8"),
        "VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES",
    )
    fixtures = {
        "piplup": {
            "id": "sm12-54", "tcgdexId": "sm12-54", "name": "Piplup", "localId": "54",
            "set": {"id": "sm12", "name": "Eclissi Cosmica"}, "rarity": "Comune",
            "variants": {"normal": True, "holo": False, "reverse": False},
            "variants_detailed": [{"type": "normal", "size": "Standard", "variantId": "generated"}],
            "pricing": {"cardmarket": {"idProduct": 398504, "trend": 54.51, "trend-holo": 11.29}},
        },
        "surging": [
            {"id": "sv08-029", "tcgdexId": "sv08-029", "localId": "29", "set": {"id": "sv08"},
             "pricing": {"cardmarket": {"idProduct": 794946}}, "variants_detailed": [
                 {"type": "normal", "thirdParty": {"cardmarket": 794286},
                  "pricing": {"cardmarket": {"idProduct": 794286, "trend": 0.11}}}]},
            {"id": "sv08-050", "tcgdexId": "sv08-050", "localId": "50", "set": {"id": "sv08"},
             "pricing": {"cardmarket": {"idProduct": 794947}}, "variants_detailed": [
                 {"type": "normal", "thirdParty": {"cardmarket": 794316},
                  "pricing": {"cardmarket": {"idProduct": 794316, "trend": 0.12}}}]},
            {"id": "sv08-161", "tcgdexId": "sv08-161", "localId": "161", "set": {"id": "sv08"},
             "pricing": {"cardmarket": {"idProduct": 794948}}, "variants_detailed": [
                 {"type": "normal", "thirdParty": {"cardmarket": 794534},
                  "pricing": {"cardmarket": {"idProduct": 794534, "trend": 0.13}}}]},
        ],
        "frillish": {"id": "sv10.5w-044", "tcgdexId": "sv10.5w-044", "name": "Frillish",
                     "localId": "044", "set": {"id": "sv10.5w", "name": "Fuoco Bianco"}},
        "exeggcute001": {"id": "sv08.5-001", "tcgdexId": "sv08.5-001", "name": "Exeggcute",
                        "localId": "001", "set": {"id": "sv08.5", "name": "Evoluzioni Prismatiche"},
                        "variant": "Poké Ball Reverse Holo", "stamp": "None"},
        "erikasGloom": {"id": "me02.5-002", "tcgdexId": "me02.5-002", "name": "Erika's Gloom",
                        "localId": "002", "set": {"id": "me02.5", "name": "Ascesa Eroica"},
                        "variant": "Poké Ball Reverse Holo", "stamp": "None"},
        "pikachu": {"id": "sv05-051", "tcgdexId": "sv05-051", "name": "Pikachu",
                    "localId": "051", "set": {"id": "sv05", "name": "Cronoforze"}},
        "articuno51": {
            "id":"sv10-051","tcgdexId":"sv10-051","name":"Articuno del Team Rocket","localId":"051",
            "set":{"id":"sv10","name":"Rivali Predestinati"},"variant":"Holo","stamp":"None",
            "variants":{"normal":True,"holo":True,"reverse":True},
            "variants_detailed":[
                {"type":"Reverse","size":"Standard","thirdParty":{"cardmarket":825925},
                 "pricing":{"cardmarket":{"idProduct":825925,"trend":0.14,"trend-holo":0.34}}},
                {"type":"Olografica","size":"Standard","thirdParty":{"cardmarket":825925},
                 "pricing":{"cardmarket":{"idProduct":825925,"trend":0.14,"trend-holo":0.34}}},
                {"type":"Normale","size":"Standard","thirdParty":{"cardmarket":871155},
                 "pricing":{"cardmarket":{"idProduct":871155,"trend":22.30}}}
            ],
            "pricing":{"cardmarket":{"idProduct":825925,"trend":0.14,"low":0.02,"avg7":0.14,"avg30":0.16,
                                     "trend-holo":0.34,"low-holo":0.02,"avg7-holo":0.31,"avg30-holo":0.35}}
        },
        "tyranitar96Ambiguous": {
            "id":"sv10-096","tcgdexId":"sv10-096","name":"Tyranitar del Team Rocket","localId":"096",
            "set":{"id":"sv10"},"variant":"Holo","stamp":"None",
            "variants":{"normal":True,"holo":True,"reverse":True},
            "variants_detailed":[
                {"type":"holo","size":"standard","thirdParty":{"cardmarket":825969},
                 "pricing":{"cardmarket":{"idProduct":825969,"trend":0.08}}},
                {"type":"holo","size":"standard","thirdParty":{"cardmarket":828209},
                 "pricing":{"cardmarket":{"idProduct":828209,"trend":1.0}}},
                {"type":"normal","size":"standard","thirdParty":{"cardmarket":828102},
                 "pricing":{"cardmarket":{"idProduct":828102,"trend":1.0}}},
                {"type":"reverse","size":"standard","thirdParty":{"cardmarket":825969},
                 "pricing":{"cardmarket":{"idProduct":825969,"trend":0.08,"trend-holo":0.29}}}
            ],
            "pricing":{"cardmarket":{"idProduct":825969,"trend":0.08,"trend-holo":0.29}}
        },
    }
    fixtures["batch2_base"] = [
        {
            "id": card_id, "tcgdexId": card_id, "name": exact_guides[card_id]["name"],
            "localId": local_id, "set": {"id": set_id}, "wrong": wrong, "correct": correct,
            "pricing": {"cardmarket": {"idProduct": wrong, "trend": 999}},
            "variants_detailed": [],
        }
        for card_id, (set_id, local_id, wrong, correct) in sorted(BATCH2_BASE_OVERRIDE_ROWS.items())
    ]
    fixtures["batch2_owners"] = [
        {
            "id": card_id, "tcgdexId": card_id, "name": name, "localId": local_id,
            "set": {"id": set_id}, "product": product,
            "pricing": {"cardmarket": {"idProduct": product, "trend": 1}},
        }
        for card_id, (set_id, local_id, name, product) in sorted(BATCH2_SHARED_PRODUCT_OWNERS.items())
    ]
    fixtures["dualBase"] = [
        {
            "id":"sv05-041","tcgdexId":"sv05-041","name":"Feraligatr","localId":"041","set":{"id":"sv05","name":"Temporal Forces"},
            "variants":{"normal":True,"holo":True,"reverse":True},
            "variants_detailed":[
                {"type":"holo","size":"standard","thirdParty":{"cardmarket":760671},"pricing":{"cardmarket":{"idProduct":760671,"trend":0.10,"low":0.02,"avg7":0.12,"avg30":0.14,"avg":0.14,"trend-holo":0.19,"low-holo":0.02,"avg7-holo":0.19,"avg30-holo":0.28,"avg-holo":0.26}}},
                {"type":"reverse","size":"standard","thirdParty":{"cardmarket":760671},"pricing":{"cardmarket":{"idProduct":760671,"trend":0.10,"low":0.02,"avg7":0.12,"avg30":0.14,"avg":0.14,"trend-holo":0.19,"low-holo":0.02,"avg7-holo":0.19,"avg30-holo":0.28,"avg-holo":0.26}}},
                {"type":"normal","size":"standard","thirdParty":{"cardmarket":761970},"pricing":{"cardmarket":{"idProduct":761970,"trend":0.84,"low":0.02,"avg7":0.81,"avg30":0.52,"avg":0.69}}},
                {"type":"normal","size":"standard","stamp":["player-rewards-program"]}
            ],
            "pricing":{"cardmarket":{"idProduct":760671,"trend":0.10,"low":0.02,"avg7":0.12,"avg30":0.14,"avg":0.14,"trend-holo":0.19,"low-holo":0.02,"avg7-holo":0.19,"avg30-holo":0.28,"avg-holo":0.26}},
            "expected":{"normal":[0.84,761970],"holo":[0.10,760671],"reverse":[0.19,760671]}
        },
        {
            "id":"sv08-065","tcgdexId":"sv08-065","name":"Tapu Koko","localId":"065","set":{"id":"sv08","name":"Surging Sparks"},
            "variants":{"normal":True,"holo":True,"reverse":True},
            "variants_detailed":[
                {"type":"holo","size":"standard","thirdParty":{"cardmarket":794346},"pricing":{"cardmarket":{"idProduct":794346,"trend":0.07,"low":0.02,"avg7":0.06,"avg30":0.05,"avg":0.05,"trend-holo":0.24,"low-holo":0.02,"avg7-holo":0.23,"avg30-holo":0.16,"avg-holo":0.13}}},
                {"type":"reverse","size":"standard","thirdParty":{"cardmarket":794346},"pricing":{"cardmarket":{"idProduct":794346,"trend":0.07,"low":0.02,"avg7":0.06,"avg30":0.05,"avg":0.05,"trend-holo":0.24,"low-holo":0.02,"avg7-holo":0.23,"avg30-holo":0.16,"avg-holo":0.13}}},
                {"type":"normal","size":"standard","thirdParty":{"cardmarket":799718},"pricing":{"cardmarket":{"idProduct":799718,"trend":0.02,"low":0.02,"avg7":1.55,"avg30":2.48,"avg":1.12}}},
                {"type":"normal","size":"standard","stamp":["player-rewards-program"]}
            ],
            "pricing":{"cardmarket":{"idProduct":794346,"trend":0.07,"low":0.02,"avg7":0.06,"avg30":0.05,"avg":0.05,"trend-holo":0.24,"low-holo":0.02,"avg7-holo":0.23,"avg30-holo":0.16,"avg-holo":0.13}},
            "expected":{"normal":[0.02,799718],"holo":[0.07,794346],"reverse":[0.24,794346]}
        },
    ]
    fixtures["tyranitar"] = {
        "id": "ecard1-66", "tcgdexId": "ecard1-66", "name": "Tyranitar", "localId": "66",
        "set": {"id": "ecard1", "name": "Expedition Base Set"}, "rarity": "Rare",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 274904}, "pricing": {"cardmarket": {"idProduct": 274904, "trend": 311.31}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 362890}, "pricing": {"cardmarket": {"idProduct": 362890, "trend": 36.28}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 274904, "trend": 311.31, "trend-holo": 136.66}},
    }
    fixtures["milotic70"] = {
        "id": "pl3-70", "tcgdexId": "pl3-70", "name": "Milotic", "localId": "70",
        "set": {"id": "pl3", "name": "Supreme Victors"}, "rarity": "Uncommon",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 882910}, "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 278689}, "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68}}},
            {"type": "normal", "stamp": ["pre-release"], "thirdParty": {"cardmarket": 882910}, "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}},
    }
    fixtures["cryogonal027"] = {
        "id": "sv10.5b-027", "tcgdexId": "sv10.5b-027", "name": "Cryogonal", "localId": "027",
        "set": {"id": "sv10.5b", "name": "Black Bolt"}, "rarity": "Uncommon", "regulationMark": "I",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 835953}},
            {"type": "reverse", "thirdParty": {"cardmarket": 835953}},
            {"type": "reverse", "foil": "pokeball", "thirdParty": {"cardmarket": 836326}},
            {"type": "reverse", "foil": "masterball", "thirdParty": {"cardmarket": 836324}},
        ],
        "pricing": {"cardmarket": {"idProduct": 835994, "trend": 0.02, "trend-holo": 0.28}},
    }
    fixtures["darmanitan014"] = {
        "id": "sv10.5b-014", "tcgdexId": "sv10.5b-014", "name": "Darmanitan", "localId": "014",
        "set": {"id": "sv10.5b", "name": "Black Bolt"}, "rarity": "Uncommon", "regulationMark": "I",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 835929}},
            {"type": "reverse", "thirdParty": {"cardmarket": 835929}},
            {"type": "reverse", "foil": "pokeball", "thirdParty": {"cardmarket": 836285}},
            {"type": "reverse", "foil": "masterball", "thirdParty": {"cardmarket": 836286}},
        ],
        "pricing": {"cardmarket": {"idProduct": 835069}},
    }
    fixtures["bisharp065"] = {
        "id": "sv10.5b-065", "tcgdexId": "sv10.5b-065", "name": "Bisharp", "localId": "065",
        "set": {"id": "sv10.5b", "name": "Black Bolt"}, "rarity": "Uncommon", "regulationMark": "I",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 836043}},
            {"type": "reverse", "thirdParty": {"cardmarket": 836043}},
            {"type": "reverse", "foil": "pokeball", "thirdParty": {"cardmarket": 836444}},
            {"type": "reverse", "foil": "masterball", "thirdParty": {"cardmarket": 836445}},
        ],
        "pricing": {"cardmarket": {"idProduct": 836009, "trend": 0.03, "trend-holo": 0.19}},
    }
    fixtures["giratina201"] = {
        "id": "swsh11-201", "tcgdexId": "swsh11-201", "name": "Giratina VSTAR", "localId": "201",
        "set": {"id": "swsh11", "name": "Lost Origin"}, "rarity": "Secret Rare", "regulationMark": "F",
        "variants": {"normal": False, "holo": True, "reverse": False},
        "variants_detailed": [
            {"type": "holo", "foil": "rainbow", "thirdParty": {"cardmarket": 670816},
             "pricing": {"cardmarket": {"idProduct": 670816, "trend": 1.46}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 670816, "trend": 1.46}},
    }
    fixtures["froakie056"] = {
        "id": "sv03-056", "tcgdexId": "sv03-056", "name": "Froakie", "localId": "056",
        "set": {"id": "sv03", "name": "Obsidian Flames"}, "rarity": "Common", "regulationMark": "G",
        "variants": {"normal": True, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "reverse", "thirdParty": {"cardmarket": 725136},
             "pricing": {"cardmarket": {"idProduct": 725136, "trend": 0.03, "avg7": 0.03, "avg30": 0.04, "avg": 0.04, "low": 0.02, "trend-holo": 0.13, "avg7-holo": 0.09, "avg30-holo": 0.12, "avg-holo": 0.13, "low-holo": 0.02}}},
            {"type": "normal", "thirdParty": {"cardmarket": 781857},
             "pricing": {"cardmarket": {"idProduct": 781857, "trend": 0.20, "avg7": 0.21, "avg30": 0.25, "avg": 0.25, "low": 0.02}}},
            {"type": "holo", "foil": "cosmos", "thirdParty": {"cardmarket": 781857},
             "pricing": {"cardmarket": {"idProduct": 781857, "trend": 0.20, "avg7": 0.21, "avg30": 0.25, "avg": 0.25, "low": 0.02}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 781857, "trend": 0.20, "avg7": 0.21, "avg30": 0.25, "avg": 0.25, "low": 0.02}},
    }
    fixtures["palafin062"] = {
        "id": "sv03-062", "tcgdexId": "sv03-062", "name": "Palafin", "localId": "062",
        "set": {"id": "sv03", "name": "Obsidian Flames"}, "rarity": "Rare", "regulationMark": "G",
        "variants": {"normal": True, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "stamp": ["pre-release"], "thirdParty": {"cardmarket": 727118},
             "pricing": {"cardmarket": {"idProduct": 727118, "trend": 0.26, "avg7": 0.23, "avg30": 0.18, "avg": 0.16, "low": 0.02}}},
            {"type": "holo", "thirdParty": {"cardmarket": 725142},
             "pricing": {"cardmarket": {"idProduct": 725142, "trend": 0.02, "avg7": 0.05, "avg30": 0.06, "avg": 0.06, "low": 0.02, "trend-holo": 0.16, "avg7-holo": 0.18, "avg30-holo": 0.25, "avg-holo": 0.24, "low-holo": 0.02}}},
            {"type": "holo", "foil": "cosmos", "thirdParty": {"cardmarket": 781858},
             "pricing": {"cardmarket": {"idProduct": 781858, "trend": 0.22}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 725142},
             "pricing": {"cardmarket": {"idProduct": 725142, "trend": 0.02, "trend-holo": 0.16}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 727118, "trend": 0.26, "avg7": 0.23, "avg30": 0.18, "avg": 0.16, "low": 0.02}},
    }
    fixtures["metagross"] = {
        "id": "pl3-7", "tcgdexId": "pl3-7", "name": "Metagross", "localId": "7",
        "set": {"id": "pl3", "name": "Supreme Victors"}, "rarity": "Rare Holo",
        "variants": {"normal": False, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "holo", "thirdParty": {"cardmarket": 278689}, "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68, "trend-holo": 62.71}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 278698}, "pricing": {"cardmarket": {"idProduct": 278698, "trend": 3.05, "trend-holo": 3.24}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68, "trend-holo": 62.71}},
    }
    fixtures["ex4_high_impact"] = [
        {"id":"ex4-6","tcgdexId":"ex4-6","name":"Team Aqua's Walrein","localId":"6","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Holo Rare","wrong":275783,"correct":275983,"expected":4.40},
        {"id":"ex4-7","tcgdexId":"ex4-7","name":"Team Magma's Aggron","localId":"7","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Holo Rare","wrong":275784,"correct":275984,"expected":5.80},
        {"id":"ex4-89","tcgdexId":"ex4-89","name":"Blaziken ex","localId":"89","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275866,"correct":276066,"expected":136.64},
        {"id":"ex4-94","tcgdexId":"ex4-94","name":"Suicune ex","localId":"94","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275871,"correct":276071,"expected":714.52},
        {"id":"ex4-95","tcgdexId":"ex4-95","name":"Swampert ex","localId":"95","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275872,"correct":276072,"expected":93.11},
    ]
    for card in fixtures["ex4_high_impact"]:
        card["variants"] = {"normal": False, "holo": True, "reverse": False}
        card["variants_detailed"] = [{"type":"holo","thirdParty":{"cardmarket":card["wrong"]},"pricing":{"cardmarket":{"idProduct":card["wrong"],"trend":1}}}]
        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}
    fixtures["ex4_verified_batch"] = [
        {"id":"ex4-19","tcgdexId":"ex4-19","name":"Team Magma's Camerupt","localId":"19","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275796,"correct":275996},
        {"id":"ex4-23","tcgdexId":"ex4-23","name":"Team Magma's Zangoose","localId":"23","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275800,"correct":276000},
        {"id":"ex4-64","tcgdexId":"ex4-64","name":"Team Magma's Numel","localId":"64","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275841,"correct":276041},
        {"id":"ex4-73","tcgdexId":"ex4-73","name":"Maxie","localId":"73","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275850,"correct":276050},
        {"id":"ex4-78","tcgdexId":"ex4-78","name":"Team Aqua Hideout","localId":"78","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275855,"correct":276055},
        {"id":"ex4-80","tcgdexId":"ex4-80","name":"Team Magma Ball","localId":"80","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275857,"correct":276057},
        {"id":"ex4-82","tcgdexId":"ex4-82","name":"Team Magma Conspirator","localId":"82","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275859,"correct":276059},
        {"id":"ex4-85","tcgdexId":"ex4-85","name":"Warp Point","localId":"85","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275862,"correct":276062},
        {"id":"ex4-87","tcgdexId":"ex4-87","name":"Magma Energy","localId":"87","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275864,"correct":276064},
        {"id":"ex4-1","tcgdexId":"ex4-1","name":"Team Aqua's Cacturne","localId":"1","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275778,"correct":275978},
        {"id":"ex4-3","tcgdexId":"ex4-3","name":"Team Aqua's Kyogre","localId":"3","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275780,"correct":275980},
        {"id":"ex4-9","tcgdexId":"ex4-9","name":"Team Magma's Groudon","localId":"9","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275786,"correct":275986},
        {"id":"ex4-12","tcgdexId":"ex4-12","name":"Team Magma's Torkoal","localId":"12","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275789,"correct":275989},
        {"id":"ex4-13","tcgdexId":"ex4-13","name":"Raichu","localId":"13","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275790,"correct":275990},
        {"id":"ex4-17","tcgdexId":"ex4-17","name":"Team Aqua's Seviper","localId":"17","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275794,"correct":275994},
        {"id":"ex4-28","tcgdexId":"ex4-28","name":"Team Aqua's Lanturn","localId":"28","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275805,"correct":276005},
        {"id":"ex4-39","tcgdexId":"ex4-39","name":"Bulbasaur","localId":"39","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275816,"correct":276016},
        {"id":"ex4-40","tcgdexId":"ex4-40","name":"Cubone","localId":"40","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275817,"correct":276017},
        {"id":"ex4-41","tcgdexId":"ex4-41","name":"Jigglypuff","localId":"41","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275818,"correct":276018},
        {"id":"ex4-42","tcgdexId":"ex4-42","name":"Meowth","localId":"42","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275819,"correct":276019},
        {"id":"ex4-43","tcgdexId":"ex4-43","name":"Pikachu","localId":"43","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275820,"correct":276020},
        {"id":"ex4-44","tcgdexId":"ex4-44","name":"Psyduck","localId":"44","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275821,"correct":276021},
        {"id":"ex4-45","tcgdexId":"ex4-45","name":"Slowpoke","localId":"45","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275822,"correct":276022},
        {"id":"ex4-46","tcgdexId":"ex4-46","name":"Squirtle","localId":"46","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275823,"correct":276023},
        {"id":"ex4-49","tcgdexId":"ex4-49","name":"Team Aqua's Chinchou","localId":"49","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275826,"correct":276026},
        {"id":"ex4-69","tcgdexId":"ex4-69","name":"Team Aqua Schemer","localId":"69","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275846,"correct":276046},
        {"id":"ex4-70","tcgdexId":"ex4-70","name":"Team Magma Schemer","localId":"70","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275847,"correct":276047},
        {"id":"ex4-71","tcgdexId":"ex4-71","name":"Archie","localId":"71","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275848,"correct":276048},
        {"id":"ex4-72","tcgdexId":"ex4-72","name":"Dual Ball","localId":"72","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275849,"correct":276049},
        {"id":"ex4-74","tcgdexId":"ex4-74","name":"Strength Charm","localId":"74","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275851,"correct":276051},
        {"id":"ex4-75","tcgdexId":"ex4-75","name":"Team Aqua Ball","localId":"75","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275852,"correct":276052},
        {"id":"ex4-76","tcgdexId":"ex4-76","name":"Team Aqua Belt","localId":"76","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275853,"correct":276053},
        {"id":"ex4-77","tcgdexId":"ex4-77","name":"Team Aqua Conspirator","localId":"77","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275854,"correct":276054},
        {"id":"ex4-79","tcgdexId":"ex4-79","name":"Team Aqua Technical Machine 01","localId":"79","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275856,"correct":276056},
        {"id":"ex4-81","tcgdexId":"ex4-81","name":"Team Magma Belt","localId":"81","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275858,"correct":276058},
        {"id":"ex4-83","tcgdexId":"ex4-83","name":"Team Magma Hideout","localId":"83","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275860,"correct":276060},
        {"id":"ex4-84","tcgdexId":"ex4-84","name":"Team Magma Technical Machine 01","localId":"84","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275861,"correct":276061},
        {"id":"ex4-86","tcgdexId":"ex4-86","name":"Aqua Energy","localId":"86","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275863,"correct":276063},
        {"id":"ex4-88","tcgdexId":"ex4-88","name":"Double Rainbow Energy","localId":"88","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275865,"correct":276065},
    ]
    for card in fixtures["ex4_verified_batch"]:
        card["variants"] = {"normal": False, "holo": True, "reverse": True}
        card["variants_detailed"] = [{"type":"holo","thirdParty":{"cardmarket":card["wrong"]},"pricing":{"cardmarket":{"idProduct":card["wrong"],"trend":1}}}]
        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}
    fixtures["mcd2019"] = [
        {
            "id": card_id, "tcgdexId": card_id, "name": rule["names"][0],
            "localId": rule["localId"], "set": {"id": "2019sm-fr"},
            "variants": {"normal": True, "holo": True, "reverse": False},
            "normalProduct": rule["normal"]["idProduct"],
            "holoProduct": rule["holo"]["idProduct"],
            "normalTrend": rule["normal"]["trend"],
            "holoTrend": rule["holo"]["trend"],
        }
        for card_id, rule in sorted(mcd2019_rules.items())
    ]
    fixtures["ex8_verified_batch"] = [
        {"id":"ex8-17","tcgdexId":"ex8-17","name":"Deoxys","localId":"17","set":{"id":"ex8"},"wrong":276419,"correct":276420,"variant":"Normal","expected":15.66},
        {"id":"ex8-18","tcgdexId":"ex8-18","name":"Deoxys","localId":"18","set":{"id":"ex8"},"wrong":276419,"correct":276421,"variant":"Normal","expected":6.22},
    ]
    for card in fixtures["ex8_verified_batch"]:
        is_holo = card["variant"] == "Holo"
        card["variants"] = {"normal": not is_holo, "holo": is_holo, "reverse": not is_holo}
        card["variants_detailed"] = [{"type":"holo" if is_holo else "normal","thirdParty":{"cardmarket":card["wrong"]}}]
        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}
    fixtures["zacianVUnion"] = {
        "id":"swshp-SWSH163","tcgdexId":"swshp-SWSH163","name":"Zacian V-UNION",
        "localId":"SWSH163","set":{"id":"swshp"},"variants":{"holo":True},
        "pricing":{"cardmarket":{"idProduct":572163,"trend":3.58}},
    }
    harness = r"""
const assert=require('assert');
const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const fixtures=JSON.parse(process.argv[2]);
function section(start,end){
  const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  assert(a>=0&&b>a,`Missing production section ${start}`);
  return source.slice(a,b);
}
const production=[
  section("function normText(","function similarity("),
  section("function canonicalPrintedLocalId(","function extractCollectorCode("),
  section("function normalizedPlaySeries(","function playSeriesLabel("),
  section("function canonicalStamp(","function scanUnit("),
  section("async function renderScanValue(","async function chooseCard("),
  section("function cardPriceInfo(","function cardUnitPrice(")
].join('\n');
const elements={};
function element(id){
  if(!elements[id])elements[id]={
    textContent:'',innerHTML:'',value:id==='variant'?'Reverse Holo':id==='stamp'?'None':'',
    classList:{add(){},remove(){},toggle(){}},style:{},options:[],selectedOptions:[]
  };
  return elements[id];
}
const context={console,document:{getElementById:element}};
vm.createContext(context);
vm.runInContext(`
${production}
let scanPriceCard=null;
let selectedCard=null;
function scanEuro(v){const n=Number(v||0);return n>0?n.toLocaleString('it-IT',{style:'currency',currency:'EUR'}):'—'}
function scanCM(c){return resolvedCardmarketPricingForCard(c)}
function verifiedStandardEnergyPrice(){return null}
async function fetchScanPricing(card){return card}
async function enrichCardoryxEnglishIdentity(){}
async function refreshOfficialPlayAvailability(){}
function refreshScanProtectionRecommendation(){}
syncStampAvailability=()=>[];
syncVariantAvailability=()=>[];
globalThis.runtime={
  verifiedDualBaseCardmarketVariant,verifiedBaseCardmarketProductOverride,resolvedCardmarketPricingForCard,
  pricingWithResolvedCardmarket,knownCardmarketIdentityConflict,
  cardmarketValueForCardVariant,cardmarketStatsForCardVariant,
  verifiedVariantPrice,verifiedStampPrice,verifiedMcdonalds2019CardmarketVariant,
  verifiedNormalFinishHoloPrice,documentedVariantsForCard,renderScanValue,cardPriceInfo,
  setSelected:c=>{selectedCard=c;scanPriceCard=null}
};`,context);
const r=context.runtime;
const articuno=fixtures.articuno51;
const articunoHolo=r.cardmarketValueForCardVariant(articuno,'Holo');
assert.strictEqual(articunoHolo.value,0.14);
assert.strictEqual(articunoHolo.productId,825925);
assert.strictEqual(articunoHolo.kind,'verified-normal-registry-holo');
assert.strictEqual(r.cardPriceInfo(articuno).value,0.14);
assert.strictEqual(r.verifiedNormalFinishHoloPrice({...articuno,localId:'052'},'Holo'),null);
assert.strictEqual(r.verifiedNormalFinishHoloPrice({...articuno,set:{id:'sv09'}},'Holo'),null);
assert.strictEqual(r.verifiedNormalFinishHoloPrice({...articuno,tcgdexId:'sv10-052',id:'sv10-052'},'Holo'),null);
const tyr96=fixtures.tyranitar96Ambiguous;
assert.strictEqual(r.verifiedNormalFinishHoloPrice(tyr96,'Holo'),null);
assert.strictEqual(r.cardmarketValueForCardVariant(tyr96,'Holo').value,0);
assert.strictEqual(r.cardmarketValueForCardVariant(tyr96,'Holo').kind,'needs-exact-variant');

const p=fixtures.piplup;
const override=r.verifiedBaseCardmarketProductOverride(p);
assert.strictEqual(override?.pricing?.idProduct,407919);
assert.strictEqual(r.resolvedCardmarketPricingForCard(p)?.idProduct,407919);
assert.strictEqual(r.knownCardmarketIdentityConflict(p,398504)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,localId:'SM54'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,tcgdexId:'sm12-55',id:'sm12-55'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,set:{...p.set,id:'sm11'}}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,name:'Prinplup'}),null);
for(const card of fixtures.dualBase){
  const normal=r.cardmarketValueForCardVariant(card,'Normal');
  const holo=r.cardmarketValueForCardVariant(card,'Holo');
  const reverse=r.cardmarketValueForCardVariant(card,'Reverse Holo');
  assert.deepStrictEqual(JSON.parse(JSON.stringify([normal.value,normal.productId])),card.expected.normal);
  assert.deepStrictEqual(JSON.parse(JSON.stringify([holo.value,holo.productId])),card.expected.holo);
  assert.deepStrictEqual(JSON.parse(JSON.stringify([reverse.value,reverse.productId])),card.expected.reverse);
  assert.strictEqual(normal.kind,'exact-dual-base-cardmarket');
  assert.strictEqual(holo.kind,'exact-dual-base-cardmarket');
  assert.strictEqual(reverse.kind,'exact-dual-base-cardmarket');
  assert.strictEqual(r.verifiedDualBaseCardmarketVariant({...card,set:{id:'wrong'}},'Normal'),null);
  assert.strictEqual(r.verifiedDualBaseCardmarketVariant({...card,localId:'999'},'Normal'),null);
  assert.strictEqual(r.verifiedDualBaseCardmarketVariant({...card,name:card.name+' wrong'},'Normal'),null);
  const stampedOnly={...card,variants_detailed:card.variants_detailed.filter(x=>Array.isArray(x.stamp)&&x.stamp.includes('player-rewards-program'))};
  const noLeak=r.verifiedDualBaseCardmarketVariant(stampedOnly,'Normal');
  assert.strictEqual(noLeak?.handled,true);
  assert.strictEqual(noLeak?.matched,false);
  const ns=r.cardmarketStatsForCardVariant(card,'Normal');
  const hs=r.cardmarketStatsForCardVariant(card,'Holo');
  const rs=r.cardmarketStatsForCardVariant(card,'Reverse Holo');
  assert.strictEqual(ns.trend,card.expected.normal[0]);
  assert.strictEqual(hs.trend,card.expected.holo[0]);
  assert.strictEqual(rs.trend,card.expected.reverse[0]);
}
const tyr=fixtures.tyranitar;
const tyrOverride=r.verifiedBaseCardmarketProductOverride(tyr);
assert.strictEqual(tyrOverride?.pricing?.idProduct,274941);
assert.strictEqual(r.resolvedCardmarketPricingForCard(tyr)?.idProduct,274941);
assert.strictEqual(r.knownCardmarketIdentityConflict(tyr,274904)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...tyr,id:'ecard1-29',tcgdexId:'ecard1-29',localId:'29'},274941)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...tyr,localId:'29'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...tyr,name:'Tyranitar ex'}),null);
const tyrNormal=r.cardmarketValueForCardVariant(tyr,'Normal');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:tyrNormal.value,productId:tyrNormal.productId})),{value:10.33,productId:274941});
const bish=fixtures.bisharp065;
const bishOverride=r.verifiedBaseCardmarketProductOverride(bish);
assert.strictEqual(bishOverride?.pricing?.idProduct,836043);
assert.strictEqual(r.resolvedCardmarketPricingForCard(bish)?.idProduct,836043);
assert.strictEqual(r.knownCardmarketIdentityConflict(bish,836009)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...bish,id:'sv10.5b-066',tcgdexId:'sv10.5b-066',localId:'066'},836043)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...bish,id:'other-1',tcgdexId:'other-1',localId:'1',name:'Other',set:{id:'other'}},836009),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...bish,localId:'066'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...bish,name:'Pawniard'}),null);
const bishNormal=r.cardmarketValueForCardVariant(bish,'Normal');
const bishReverse=r.cardmarketValueForCardVariant(bish,'Reverse Holo');
const bishPoke=r.cardmarketValueForCardVariant(bish,'Poké Ball Reverse Holo');
const bishMaster=r.cardmarketValueForCardVariant(bish,'Master Ball Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:bishNormal.value,productId:bishNormal.productId})),{value:0.03,productId:836043});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:bishReverse.value,productId:bishReverse.productId})),{value:0.12,productId:836043});
assert.strictEqual(bishPoke.value,0);
assert.strictEqual(bishPoke.kind,'needs-exact-variant');
assert.strictEqual(bishMaster.value,0);
assert.strictEqual(bishMaster.kind,'needs-exact-variant');
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(bish,'Normal'))),{low:0.02,trend:0.03,avg7:0.03,avg30:0.03});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(bish,'Reverse Holo'))),{low:0.02,trend:0.12,avg7:0.15,avg30:0.16});
const gir=fixtures.giratina201;
const girOverride=r.verifiedBaseCardmarketProductOverride(gir);
assert.strictEqual(girOverride?.pricing?.idProduct,674207);
assert.strictEqual(r.resolvedCardmarketPricingForCard(gir)?.idProduct,674207);
assert.strictEqual(r.knownCardmarketIdentityConflict(gir,670816)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...gir,id:'swsh11-202',tcgdexId:'swsh11-202',localId:'202'},674207)?.kind,'identity-mismatch');
const correctGiratinaV={...gir,id:'swsh11-130',tcgdexId:'swsh11-130',name:'Giratina V',localId:'130',variants_detailed:[{type:'holo',thirdParty:{cardmarket:670816}}],pricing:{cardmarket:{idProduct:670816,trend:1.46}}};
assert.strictEqual(r.knownCardmarketIdentityConflict(correctGiratinaV,670816),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...gir,localId:'202'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...gir,name:'Giratina V'}),null);
const girHolo=r.cardmarketValueForCardVariant(gir,'Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:girHolo.value,productId:girHolo.productId,kind:girHolo.kind})),{value:20.65,productId:674207,kind:'exact-giratina-vstar-201'});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(gir,'Holo'))),{low:9.9,trend:20.65,avg7:20.82,avg30:19.59});
const girWrongFinish=r.cardmarketValueForCardVariant(gir,'Normal');
assert.strictEqual(girWrongFinish.value,0);
assert.strictEqual(girWrongFinish.kind,'needs-exact-variant');
const girUpstreamChanged={...gir,variants_detailed:[{type:'holo',foil:'rainbow',thirdParty:{cardmarket:674207}}]};
const changedResult=r.cardmarketValueForCardVariant(girUpstreamChanged,'Holo');
assert.strictEqual(changedResult.value,0);
assert.strictEqual(changedResult.kind,'needs-exact-variant');
const fro=fixtures.froakie056;
const froOverride=r.verifiedBaseCardmarketProductOverride(fro);
assert.strictEqual(froOverride?.pricing?.idProduct,725136);
assert.strictEqual(r.resolvedCardmarketPricingForCard(fro)?.idProduct,725136);
assert.strictEqual(r.knownCardmarketIdentityConflict(fro,781857),null);
assert.strictEqual(r.knownCardmarketIdentityConflict({...fro,id:'sv03-057',tcgdexId:'sv03-057',localId:'057',name:'Frogadier'},781857)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...fro,id:'sv03-055',tcgdexId:'sv03-055',localId:'055',name:'Buizel'},725136)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...fro,localId:'057'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...fro,name:'Frogadier'}),null);
const froFinishes=[...r.documentedVariantsForCard(fro,'None','')];
assert(froFinishes.includes('Normal'));
assert(froFinishes.includes('Reverse Holo'));
assert(froFinishes.includes('Cosmos Holo'));
const froNormal=r.cardmarketValueForCardVariant(fro,'Normal');
const froReverse=r.cardmarketValueForCardVariant(fro,'Reverse Holo');
const froCosmos=r.cardmarketValueForCardVariant(fro,'Cosmos Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:froNormal.value,productId:froNormal.productId})),{value:0.03,productId:725136});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:froReverse.value,productId:froReverse.productId})),{value:0.13,productId:725136});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:froCosmos.value,productId:froCosmos.productId,kind:froCosmos.kind})),{value:0.2,productId:781857,kind:'exact-froakie-056-cosmos'});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(fro,'Normal'))),{low:0.02,trend:0.03,avg7:0.03,avg30:0.04});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(fro,'Reverse Holo'))),{low:0.02,trend:0.13,avg7:0.09,avg30:0.12});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(fro,'Cosmos Holo'))),{low:0.02,trend:0.2,avg7:0.21,avg30:0.25});
const froNoCosmosRow={...fro,variants_detailed:fro.variants_detailed.filter(x=>!/cosmos/i.test(String(x.foil||'')))};
const froFailClosed=r.cardmarketValueForCardVariant(froNoCosmosRow,'Cosmos Holo');
assert.strictEqual(froFailClosed.value,0);
assert.strictEqual(froFailClosed.kind,'needs-exact-variant');
const pal=fixtures.palafin062;
const palOverride=r.verifiedBaseCardmarketProductOverride(pal);
assert.strictEqual(palOverride?.pricing?.idProduct,725142);
assert.strictEqual(r.resolvedCardmarketPricingForCard(pal)?.idProduct,725142);
assert.strictEqual(r.knownCardmarketIdentityConflict(pal,781858)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...pal,id:'sv03-057',tcgdexId:'sv03-057',localId:'057',name:'Frogadier'},781858),null);
assert.strictEqual(r.knownCardmarketIdentityConflict({...pal,id:'other-1',tcgdexId:'other-1',localId:'1',name:'Other',set:{id:'other'}},725142)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...pal,localId:'063'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...pal,name:'Finizen'}),null);
const palBaseFinishes=[...r.documentedVariantsForCard(pal,'None','')];
assert(palBaseFinishes.includes('Holo'));
assert(palBaseFinishes.includes('Reverse Holo'));
assert(!palBaseFinishes.includes('Normal'));
assert(!palBaseFinishes.includes('Cosmos Holo'));
const palPreFinishes=[...r.documentedVariantsForCard(pal,'Pre-release','')];
assert(palPreFinishes.includes('Normal'));
const palHolo=r.cardmarketValueForCardVariant(pal,'Holo');
const palReverse=r.cardmarketValueForCardVariant(pal,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:palHolo.value,productId:palHolo.productId})),{value:0.02,productId:725142});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:palReverse.value,productId:palReverse.productId})),{value:0.16,productId:725142});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(pal,'Holo'))),{low:0.02,trend:0.02,avg7:0.05,avg30:0.06});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(pal,'Reverse Holo'))),{low:0.02,trend:0.16,avg7:0.18,avg30:0.25});
const palPre=r.verifiedStampPrice(pal,'Normal','Pre-release');
assert.strictEqual(palPre?.productId,727118);
assert.strictEqual(palPre?.trend,0.26);
assert.strictEqual(r.verifiedStampPrice(pal,'Holo','Pre-release'),null);
assert.strictEqual(r.verifiedStampPrice(pal,'Normal','None'),null);
const palSaved={...pal,pricing:r.pricingWithResolvedCardmarket(pal),variant:'Normal',stamp:'Pre-release',_cardoryxSetId:'sv03'};
assert.strictEqual(palSaved.pricing.cardmarket.idProduct,725142);
assert.strictEqual(r.cardPriceInfo(palSaved).value,0.26);
const met=fixtures.metagross;
const metOverride=r.verifiedBaseCardmarketProductOverride(met);
assert.strictEqual(metOverride?.pricing?.idProduct,278698);
assert.strictEqual(r.resolvedCardmarketPricingForCard(met)?.idProduct,278698);
assert.strictEqual(r.knownCardmarketIdentityConflict(met,278689)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...met,id:'pl3-8',tcgdexId:'pl3-8',localId:'8'},278698)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...met,localId:'8'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...met,name:'Milotic'}),null);
const metHolo=r.cardmarketValueForCardVariant(met,'Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:metHolo.value,productId:metHolo.productId})),{value:3.05,productId:278698});
const mil=fixtures.milotic70;
const milOverride=r.verifiedBaseCardmarketProductOverride(mil);
assert.strictEqual(milOverride?.pricing?.idProduct,278761);
assert.strictEqual(r.resolvedCardmarketPricingForCard(mil)?.idProduct,278761);
assert.strictEqual(r.knownCardmarketIdentityConflict(mil,278689)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...mil,id:'pl3-SH7',tcgdexId:'pl3-SH7',localId:'SH7'},278761)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...mil,localId:'71'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...mil,name:'Milotic Lv.52'}),null);
const milNormal=r.cardmarketValueForCardVariant(mil,'Normal');
const milReverse=r.cardmarketValueForCardVariant(mil,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:milNormal.value,productId:milNormal.productId})),{value:0.97,productId:278761});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:milReverse.value,productId:milReverse.productId})),{value:14.54,productId:278761});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Normal'))),{low:0.13,trend:0.97,avg7:1.27,avg30:0.87});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Reverse Holo'))),{low:0.49,trend:14.54,avg7:13.73,avg30:8.01});
const cry=fixtures.cryogonal027;
const cryOverride=r.verifiedBaseCardmarketProductOverride(cry);
assert.strictEqual(cryOverride?.pricing?.idProduct,835953);
assert.strictEqual(r.resolvedCardmarketPricingForCard(cry)?.idProduct,835953);
assert.strictEqual(r.knownCardmarketIdentityConflict(cry,835994)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...cry,id:'sv10.5b-028',tcgdexId:'sv10.5b-028',localId:'028'},835953)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...cry,localId:'028'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...cry,name:'Golurk'}),null);
const cryNormal=r.cardmarketValueForCardVariant(cry,'Normal');
const cryReverse=r.cardmarketValueForCardVariant(cry,'Reverse Holo');
const cryPoke=r.cardmarketValueForCardVariant(cry,'Poké Ball Reverse Holo');
const cryMaster=r.cardmarketValueForCardVariant(cry,'Master Ball Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:cryNormal.value,productId:cryNormal.productId})),{value:0.05,productId:835953});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:cryReverse.value,productId:cryReverse.productId})),{value:0.18,productId:835953});
assert.strictEqual(cryPoke.value,0);
assert.strictEqual(cryPoke.kind,'needs-exact-variant');
assert.strictEqual(cryMaster.value,0);
assert.strictEqual(cryMaster.kind,'needs-exact-variant');
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(cry,'Normal'))),{low:0.02,trend:0.05,avg7:0.08,avg30:0.04});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(cry,'Reverse Holo'))),{low:0.02,trend:0.18,avg7:0.20,avg30:0.19});
const dar=fixtures.darmanitan014;
const darOverride=r.verifiedBaseCardmarketProductOverride(dar);
assert.strictEqual(darOverride?.pricing?.idProduct,835929);
assert.strictEqual(r.resolvedCardmarketPricingForCard(dar)?.idProduct,835929);
assert.strictEqual(r.knownCardmarketIdentityConflict(dar,835069)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...dar,id:'sv10.5b-015',tcgdexId:'sv10.5b-015',localId:'015'},835929)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...dar,id:'other-1',tcgdexId:'other-1',localId:'1',name:'Other',set:{id:'other'}},835069),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...dar,localId:'015'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...dar,name:'Darumaka'}),null);
const darNormal=r.cardmarketValueForCardVariant(dar,'Normal');
const darReverse=r.cardmarketValueForCardVariant(dar,'Reverse Holo');
const darPoke=r.cardmarketValueForCardVariant(dar,'Poké Ball Reverse Holo');
const darMaster=r.cardmarketValueForCardVariant(dar,'Master Ball Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:darNormal.value,productId:darNormal.productId})),{value:0.03,productId:835929});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:darReverse.value,productId:darReverse.productId})),{value:0.20,productId:835929});
assert.strictEqual(darPoke.value,0);
assert.strictEqual(darPoke.kind,'needs-exact-variant');
assert.strictEqual(darMaster.value,0);
assert.strictEqual(darMaster.kind,'needs-exact-variant');
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(dar,'Normal'))),{low:0.02,trend:0.03,avg7:0.02,avg30:0.03});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(dar,'Reverse Holo'))),{low:0.02,trend:0.20,avg7:0.26,avg30:0.25});
for(const card of fixtures.ex4_high_impact){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'x',tcgdexId:card.tcgdexId+'x',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
  const value=r.cardmarketValueForCardVariant(card,'Holo');
  assert.deepStrictEqual(JSON.parse(JSON.stringify({value:value.value,productId:value.productId})),{value:card.expected,productId:card.correct});
}
for(const card of fixtures.ex4_verified_batch){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'-wrong',tcgdexId:card.tcgdexId+'-wrong',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
}
for(const card of fixtures.ex8_verified_batch){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'-wrong',tcgdexId:card.tcgdexId+'-wrong',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
  const value=r.cardmarketValueForCardVariant(card,card.variant);
  assert.deepStrictEqual(JSON.parse(JSON.stringify({value:value.value,productId:value.productId})),{value:card.expected,productId:card.correct});
}
for(const card of fixtures.batch2_base){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'-other',tcgdexId:card.tcgdexId+'-other'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,set:{id:card.set.id+'-other'}}),null);
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,localId:card.localId+'X'}),null);
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
}
for(const card of fixtures.batch2_owners){
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.product),null);
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'-other',tcgdexId:card.tcgdexId+'-other'},card.product)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,set:{id:card.set.id+'-other'}},card.product)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,localId:card.localId+'X'},card.product)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,name:card.name+' wrong'},card.product)?.kind,'identity-mismatch');
}
const ex8Deoxys16={id:'ex8-16',tcgdexId:'ex8-16',name:'Deoxys',localId:'16',set:{id:'ex8'},pricing:{cardmarket:{idProduct:276419,trend:2}}};
const ex8Rayquaza22={id:'ex8-22',tcgdexId:'ex8-22',name:'Rayquaza',localId:'22',set:{id:'ex8'},pricing:{cardmarket:{idProduct:276425,trend:3}}};
assert.strictEqual(r.knownCardmarketIdentityConflict(ex8Deoxys16,276419),null);
assert.strictEqual(r.knownCardmarketIdentityConflict(ex8Rayquaza22,276425),null);
assert.strictEqual(r.knownCardmarketIdentityConflict({...ex8Deoxys16,localId:'17'},276419)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...ex8Rayquaza22,localId:'107'},276425)?.kind,'identity-mismatch');
for(const [id,local,name,product] of [['ex8-98','98','Deoxys ex',276419],['ex8-99','99','Deoxys ex',276419],['ex8-107','107','Rayquaza ☆',276425]]){
  assert.strictEqual(r.knownCardmarketIdentityConflict({id,tcgdexId:id,localId:local,name,set:{id:'ex8'}},product)?.kind,'identity-mismatch');
}
for(const card of fixtures.mcd2019){
  const normal=r.verifiedMcdonalds2019CardmarketVariant(card,'Normal');
  const holo=r.verifiedMcdonalds2019CardmarketVariant(card,'Holo');
  assert.strictEqual(normal?.productId,card.normalProduct);
  assert.strictEqual(holo?.productId,card.holoProduct);
  assert.strictEqual(r.cardmarketValueForCardVariant(card,'Normal').value,card.normalTrend);
  assert.strictEqual(r.cardmarketValueForCardVariant(card,'Holo').value,card.holoTrend);
  assert.strictEqual(r.cardmarketValueForCardVariant(card,'Reverse Holo').value,0);
  assert.strictEqual(r.verifiedMcdonalds2019CardmarketVariant({...card,id:card.id+'x',tcgdexId:card.tcgdexId+'x'},'Normal'),null);
  assert.strictEqual(r.verifiedMcdonalds2019CardmarketVariant({...card,set:{id:'2019sm-fr-wrong'}},'Normal')?.matched,false);
  assert.strictEqual(r.verifiedMcdonalds2019CardmarketVariant({...card,localId:'999'},'Normal')?.matched,false);
  assert.strictEqual(r.verifiedMcdonalds2019CardmarketVariant({...card,name:card.name+' wrong'},'Normal')?.matched,false);
}
const zacian=fixtures.zacianVUnion;
assert.strictEqual(r.knownCardmarketIdentityConflict(zacian,572163),null);
assert.strictEqual(r.knownCardmarketIdentityConflict(zacian,576915)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...zacian,id:'swshp-SWSH164',tcgdexId:'swshp-SWSH164',localId:'SWSH164'},572163)?.kind,'identity-mismatch');
const normal=r.cardmarketValueForCardVariant(p,'Normal');
const reverse=r.cardmarketValueForCardVariant(p,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:normal.value,productId:normal.productId})),{value:0.17,productId:407919});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:reverse.value,productId:reverse.productId})),{value:0.76,productId:407919});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(p,'Normal'))),
  {low:0.02,trend:0.17,avg7:0.18,avg30:0.12});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(p,'Reverse Holo'))),
  {low:0.14,trend:0.76,avg7:0.94,avg30:0.76});
const savedPricing=r.pricingWithResolvedCardmarket(p);
assert.strictEqual(savedPricing.cardmarket.idProduct,407919);
assert.notStrictEqual(savedPricing.cardmarket.idProduct,398504);
const saved={...p,pricing:savedPricing,variant:'Reverse Holo',stamp:'None',_cardoryxSetId:'sm12'};
assert.strictEqual(r.cardPriceInfo(saved).value,0.76);
r.setSelected(p);
element('variant').value='Reverse Holo';
element('stamp').value='None';
(async()=>{
  await r.renderScanValue(p);
  assert(!element('scanMarketValue').textContent.includes('Valore da verificare'));
  assert(element('scanMarketValue').textContent.includes('0,76'));
  const expectedSurging={"sv08-029":794286,"sv08-050":794316,"sv08-161":794534};
  for(const card of fixtures.surging){
    assert.strictEqual(r.verifiedBaseCardmarketProductOverride(card)?.pricing?.idProduct,expectedSurging[card.id]);
    assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,expectedSurging[card.id]);
  }
  const frillish=r.verifiedVariantPrice(fixtures.frillish,'Master Ball Reverse Holo');
  assert.strictEqual(frillish?.productId,836574);
  assert.strictEqual(frillish?.trend,3);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.frillish,'Normal'),null);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.frillish,'Poké Ball Reverse Holo'),null);
  const exeggcute=r.verifiedVariantPrice(fixtures.exeggcute001,'Poké Ball Reverse Holo');
  assert.strictEqual(exeggcute?.productId,806408);
  assert.strictEqual(exeggcute?.trend,0.25);
  assert.strictEqual(r.cardPriceInfo(fixtures.exeggcute001).value,0.25);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.exeggcute001,'Normal'),null);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.exeggcute001,'Reverse Holo'),null);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.exeggcute001,'Master Ball Reverse Holo'),null);
  assert.strictEqual(r.verifiedVariantPrice({...fixtures.exeggcute001,localId:'002'},'Poké Ball Reverse Holo'),null);
  assert.strictEqual(r.verifiedVariantPrice({...fixtures.exeggcute001,set:{id:'sv08.5-other'}},'Poké Ball Reverse Holo'),null);
  assert.strictEqual(r.verifiedVariantPrice({...fixtures.exeggcute001,name:'Exeggutor'},'Poké Ball Reverse Holo'),null);
  const gloom=r.verifiedVariantPrice(fixtures.erikasGloom,'Poké Ball Reverse Holo');
  assert.strictEqual(gloom?.productId,870138);
  assert.strictEqual(gloom?.trend,0.13);
  const gloomIt={...fixtures.erikasGloom,name:'Gloom di Erika'};
  const gloomItalian=r.verifiedVariantPrice(gloomIt,'Poké Ball Reverse Holo');
  assert.strictEqual(gloomItalian?.productId,870138);
  assert.strictEqual(gloomItalian?.trend,0.13);
  assert.strictEqual(r.cardPriceInfo(gloomIt).value,0.13);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.erikasGloom,'Normal'),null);
  assert.strictEqual(r.verifiedVariantPrice({...fixtures.erikasGloom,localId:'003'},'Poké Ball Reverse Holo'),null);
  assert.strictEqual(r.verifiedVariantPrice({...fixtures.erikasGloom,set:{id:'me02.5-other'}},'Poké Ball Reverse Holo'),null);
  assert.strictEqual(r.verifiedVariantPrice({...fixtures.erikasGloom,name:"Erika's Oddish"},'Poké Ball Reverse Holo'),null);
  assert.strictEqual(r.cardPriceInfo(fixtures.erikasGloom).value,0.13);
  const pikachu=r.verifiedStampPrice(fixtures.pikachu,'Holo','Pokémon Day');
  assert.strictEqual(pikachu?.productId,870424);
  assert.strictEqual(pikachu?.trend,3.88);
  assert.strictEqual(r.verifiedStampPrice(fixtures.pikachu,'Normal','Pokémon Day'),null);
  assert.strictEqual(r.verifiedStampPrice(fixtures.pikachu,'Holo','None'),null);
  process.stdout.write(JSON.stringify({
    piplup:{normal,reverse,scanner:element('scanMarketValue').textContent,savedProductId:savedPricing.cardmarket.idProduct},
    surging:Object.fromEntries(fixtures.surging.map(c=>[c.id,r.resolvedCardmarketPricingForCard(c).idProduct])),
    frillish:{productId:frillish.productId,value:frillish.trend},
    exeggcute001:{productId:exeggcute.productId,value:r.cardPriceInfo(fixtures.exeggcute001).value},
    erikasGloom:{productId:gloom.productId,value:r.cardPriceInfo(fixtures.erikasGloom).value},
    pikachu:{productId:pikachu.productId,value:pikachu.trend}
  }));
})().catch(error=>{console.error(error);process.exit(1)});
"""
    output = subprocess.check_output(
        ["node", "-e", harness, str(INDEX), json.dumps(fixtures, ensure_ascii=False)],
        text=True,
    )
    return json.loads(output)


def runtime_svp_set_logo_staff_regression():
    # Verify exact live SVP Set Stamp/Staff product separation in production JS.
    source = INDEX.read_text(encoding="utf-8")

    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker:
            raise AssertionError(f"Missing production function {name}")
        brace = source.find("{", marker.start())
        depth = 0
        quote = None
        escape = False
        for i in range(brace, len(source)):
            ch = source[i]
            if quote:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = None
                continue
            if ch in "'\"`":
                quote = ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[marker.start():i + 1]
        raise AssertionError(f"Unclosed production function {name}")

    cache = Path(tempfile.gettempdir()) / "cardoryx_svp_stamp_regression_cache_v1"
    fixtures, errors = {}, {}
    for card_id in ("svp-005", "svp-006", "svp-007", "svp-045", "svp-067", "svp-101", "svp-150"):
        value, error = live_card(card_id, cache)
        if value:
            fixtures[card_id] = value
        if error:
            errors[card_id] = error
    if errors or len(fixtures) != 7:
        raise AssertionError(f"SVP live regression unavailable: {errors}")

    names = (
        "normText", "canonicalVariant", "canonicalStamp", "canonicalFinishTypeLabel",
        "canonicalFinishFoilLabel", "tcgdexVariantDetails", "stampEvidenceFromTCGdex",
        "tcgdexStampedRowFinish", "tcgdexExactSvpStampPrice",
    )
    js = "\n".join(extract_fn(name) for name in names)
    harness = r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
const checked={};
for(const id of ['svp-005','svp-006','svp-007']){
  const c=fixtures[id], rows=tcgdexVariantDetails(c);
  const setRow=rows.find(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRow=rows.find(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(!setRow||!staffRow)fail(id+' missing exact source pair');
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  const setPid=Number(setRow?.thirdParty?.cardmarket||0), staffPid=Number(staffRow?.thirdParty?.cardmarket||0);
  if(!setPrice||Number(setPrice.idProduct)!==setPid)fail(id+' Set Stamp product mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==staffPid)fail(id+' Staff product mismatch');
  if(setPid===staffPid)fail(id+' products are not distinct');
  if(!stampEvidenceFromTCGdex(c,'Set Stamp')||!stampEvidenceFromTCGdex(c,'Staff'))fail(id+' stamp evidence missing');
  const staffOnly={...c,variants_detailed:[staffRow]};
  if(stampEvidenceFromTCGdex(staffOnly,'Set Stamp'))fail(id+' Staff leaked into Set Stamp');
  checked[id]={setFinish,staffFinish,setPid,staffPid};
}
for(const id of ['svp-045','svp-067','svp-101','svp-150']){
  const c=fixtures[id];
  for(const finish of ['Normal','Holo','Reverse Holo','Cosmos Holo']){
    if(tcgdexExactSvpStampPrice(c,finish,'Set Stamp')!==null)fail(id+' unexpected Set Stamp auto-price');
    if(tcgdexExactSvpStampPrice(c,finish,'Staff')!==null)fail(id+' unexpected Staff auto-price');
  }
}
const foreign={...fixtures['svp-005'],set:{...(fixtures['svp-005'].set||{}),id:'sv01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('resolver leaked outside svp');
process.stdout.write(JSON.stringify({checked,failClosed:['svp-045','svp-067','svp-101','svp-150'],setScopeRejected:true}));
'''
    result = json.loads(subprocess.check_output(
        ["node", "-e", js + "\n" + harness, json.dumps(fixtures, ensure_ascii=False)], text=True
    ))
    verified = extract_fn("verifiedStampPrice")
    if "tcgdexExactSvpStampPrice(card,variant,stamp)" not in verified:
        raise AssertionError("verifiedStampPrice does not consume exact SVP stamp evidence")
    if verified.find("verifiedExactSpecialStampPrice") > verified.find("tcgdexExactSvpStampPrice"):
        raise AssertionError("dynamic SVP resolver precedes existing exact static registry")
    return result


def runtime_mep_set_logo_staff_regression():
    # Verify all currently audited MEP Set Stamp/Staff product pairs in production JS.
    source = INDEX.read_text(encoding="utf-8")

    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker:
            raise AssertionError(f"Missing production function {name}")
        brace = source.find("{", marker.end())
        depth = 0
        quote = None
        esc = False
        for i in range(brace, len(source)):
            ch = source[i]
            if quote:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[marker.start():i + 1]
        raise AssertionError(f"Unclosed production function {name}")

    names = (
        "normText", "canonicalStamp", "canonicalVariant", "canonicalFinishTypeLabel",
        "canonicalFinishFoilLabel", "tcgdexVariantDetails", "tcgdexStampedRowFinish",
        "tcgdexExactSvpStampPrice",
    )
    js = "\n".join(extract_fn(name) for name in names)
    ids = (
        "mep-001", "mep-002", "mep-003", "mep-004",
        "mep-014", "mep-015", "mep-016", "mep-017",
        "mep-064", "mep-065", "mep-066", "mep-067",
        "mep-074", "mep-075", "mep-076", "mep-077",
    )
    cache = Path(tempfile.gettempdir()) / "cardoryx_mep_stamp_regression_cache_v1"
    fixtures, errors = {}, {}
    for card_id in ids:
        value, error = live_card(card_id, cache)
        if value:
            fixtures[card_id] = value
        if error:
            errors[card_id] = error
    if errors or set(fixtures) != set(ids):
        raise AssertionError(f"MEP live fixture errors: {errors}; fetched={sorted(fixtures)}")

    harness = r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
function pid(r){return Number(r?.thirdParty?.cardmarket||0)}
function ppid(r){return Number(r?.pricing?.cardmarket?.idProduct||r?.pricing?.cardmarket?.id_product||0)}
const checked={};
for(const [id,c] of Object.entries(fixtures)){
  const rows=tcgdexVariantDetails(c);
  const setRows=rows.filter(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRows=rows.filter(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(setRows.length!==1||staffRows.length!==1)fail(id+' source pair not unique');
  const setRow=setRows[0], staffRow=staffRows[0];
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  if(!(pid(setRow)>0)||pid(setRow)!==ppid(setRow))fail(id+' invalid Set Stamp product');
  if(!(pid(staffRow)>0)||pid(staffRow)!==ppid(staffRow))fail(id+' invalid Staff product');
  if(pid(setRow)===pid(staffRow))fail(id+' Set Stamp/Staff product collision');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  if(!setPrice||Number(setPrice.idProduct)!==pid(setRow))fail(id+' Set Stamp resolver mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==pid(staffRow))fail(id+' Staff resolver mismatch');
  checked[id]={setFinish,staffFinish,setPid:pid(setRow),staffPid:pid(staffRow)};
}
const foreign={...fixtures['mep-001'],set:{...(fixtures['mep-001'].set||{}),id:'me01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('resolver leaked outside verified promo sets');
process.stdout.write(JSON.stringify({checked,count:Object.keys(checked).length,setScopeRejected:true}));
'''
    result = json.loads(subprocess.check_output(
        ["node", "-e", js + "\n" + harness, json.dumps(fixtures)],
        text=True,
    ))
    if result.get("count") != 16 or not result.get("setScopeRejected"):
        raise AssertionError(f"Unexpected MEP runtime result: {result}")
    return result


def runtime_ex5_beldum_gym_challenge_regression():
    source = INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{", marker.end()); depth=0; quote=None; esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'", '"', "`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    card,error=live_card("ex5-29", Path(tempfile.gettempdir())/"cardoryx_ex5_beldum_gym_v1")
    if error or not card: raise AssertionError(f"Beldum ex5-29 live fixture unavailable: {error}")
    rows=card.get("variants_detailed") or []
    base=[r for r in rows if not (r.get("stamp") or []) and cm_id(r)==276103 and int(((r.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)==276103]
    gym=[r for r in rows if [str(x).lower() for x in (r.get("stamp") or [])]==["gym-challenge"] and cm_id(r)==280585 and int(((r.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)==280585]
    if len(base)!=1 or len(gym)!=1: raise AssertionError(f"Unexpected Beldum product rows base={len(base)} gym={len(gym)}")
    base_cm=(base[0].get("pricing") or {}).get("cardmarket") or {}
    if not any(isinstance(base_cm.get(k),(int,float)) and base_cm.get(k)>0 for k in ("trend","avg7","avg30","avg","low")):
        raise AssertionError("Beldum base V1 has no real Cardmarket price")
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel",
           "cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails",
           "tcgdexExactEx5BeldumGymChallengePrice")
    js="\n".join(extract_fn(n) for n in names)
    harness=r'''
const c=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
if(canonicalStamp('gym-challenge')!=='Gym Challenge')fail('taxonomy not canonicalized');
const ok=tcgdexExactEx5BeldumGymChallengePrice(c,'Normal','Gym Challenge');
if(!ok||Number(ok.idProduct)!==280585)fail('exact Gym Challenge product not resolved');
for(const [v,s] of [['Reverse Holo','Gym Challenge'],['Normal','None'],['Normal','GameStop']]){
  if(tcgdexExactEx5BeldumGymChallengePrice(c,v,s)!==null)fail('wrong finish/stamp accepted '+v+' '+s);
}
for(const mutated of [
  {...c,id:'ex5-30',tcgdexId:'ex5-30'},
  {...c,localId:'030'},
  {...c,name:'Beldum wrong'},
  {...c,set:{...(c.set||{}),id:'ex5-other'}},
]) if(tcgdexExactEx5BeldumGymChallengePrice(mutated,'Normal','Gym Challenge')!==null)fail('wrong identity accepted');
const wrongPid={...c,variants_detailed:(c.variants_detailed||[]).map(r=>(r.stamp||[]).includes('gym-challenge')?{...r,thirdParty:{...(r.thirdParty||{}),cardmarket:280586}}:r)};
if(tcgdexExactEx5BeldumGymChallengePrice(wrongPid,'Normal','Gym Challenge')!==null)fail('wrong product accepted');
process.stdout.write(JSON.stringify({baseProductId:276103,gymProductId:ok.idProduct,baseTrend:Number(process.argv[2]),gymTrend:Number(ok.trend||0),exact:true}));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(card),str(base_cm.get("trend") or 0)],text=True))


def runtime_swsh028_gamestop_regression():
    source = INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{", marker.end()); depth=0; quote=None; esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'", '"', "`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    card,error=live_card("swshp-SWSH028", Path(tempfile.gettempdir())/"cardoryx_swsh028_gamestop_v1")
    if error or not card: raise AssertionError(f"SWSH028 live fixture unavailable: {error}")
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel",
           "cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails","tcgdexExactSwsh028GameStopPrice")
    js="\n".join(extract_fn(n) for n in names)
    harness=r'''
const c=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
const ok=tcgdexExactSwsh028GameStopPrice(c,'Holo','GameStop');
if(!ok||Number(ok.idProduct)!==742039)fail('exact GameStop product not resolved');
if(!Number(ok.low)>0 && !Number(ok.trend)>0)fail('no real price');
for(const [v,s] of [['Normal','GameStop'],['Holo','EB Games'],['Holo','None']]){
  if(tcgdexExactSwsh028GameStopPrice(c,v,s)!==null)fail('wrong finish/stamp accepted '+v+' '+s);
}
for(const mutated of [
  {...c,id:'swshp-SWSH029',tcgdexId:'swshp-SWSH029'},
  {...c,localId:'SWSH029'},
  {...c,name:'Duraludon wrong'},
  {...c,set:{...(c.set||{}),id:'swshp-other'}},
]) if(tcgdexExactSwsh028GameStopPrice(mutated,'Holo','GameStop')!==null)fail('wrong identity accepted');
const wrongPid={...c,variants_detailed:(c.variants_detailed||[]).map(r=>(r.stamp||[]).includes('gamestop')?{...r,thirdParty:{...(r.thirdParty||{}),cardmarket:742040}}:r)};
if(tcgdexExactSwsh028GameStopPrice(wrongPid,'Holo','GameStop')!==null)fail('wrong product accepted');
process.stdout.write(JSON.stringify({productId:ok.idProduct,trend:ok.trend,low:ok.low,exact:true}));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(card)],text=True))


def runtime_mfb_pokeball_regression():
    source=INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker=re.search(rf"\bfunction\s+{re.escape(name)}\s*\(",source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{",marker.end());depth=0;quote=None;esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'",'"',"`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    ids=list(MFB_POKEBALL_EXACT_ROWS)+["mfb-9"]
    fixtures={};errors={};cache=Path(tempfile.gettempdir())/"cardoryx_mfb_pokeball_regression_v1"
    for card_id in ids:
        value,error=live_card(card_id,cache)
        if value: fixtures[card_id]=value
        if error: errors[card_id]=error
    if errors or len(fixtures)!=len(ids): raise AssertionError(f"MFB live regression unavailable: {errors}")
    start=source.index("const VERIFIED_MFB_POKEBALL_ROWS=")
    end=source.index("const VERIFIED_PRIMARY_WORLDS_STAMPS=",start)
    registry=source[start:end]
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel","cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails","tcgdexExactMfbPokeballPrice")
    js="\n".join(extract_fn(n) for n in names if n!="tcgdexExactMfbPokeballPrice")+"\n"+registry+"\n"+extract_fn("tcgdexExactMfbPokeballPrice")
    harness=r'''
const fixtures=JSON.parse(process.argv[1]);
const rules=JSON.parse(process.argv[2]);
function fail(m){throw new Error(m)}
if(canonicalStamp('MFB Poké Ball')!=='MFB Poké Ball')fail('taxonomy not canonicalized');
const out={};
for(const [id,rule] of Object.entries(rules)){
  const c=fixtures[id];
  const ok=tcgdexExactMfbPokeballPrice(c,'Normal','MFB Poké Ball');
  if(!ok||Number(ok.idProduct)!==Number(rule.pokeball))fail(id+' exact Poké Ball product mismatch');
  if(tcgdexExactMfbPokeballPrice(c,'Holo','MFB Poké Ball')!==null)fail(id+' wrong finish accepted');
  if(tcgdexExactMfbPokeballPrice(c,'Normal','None')!==null)fail(id+' None stamp accepted');
  if(tcgdexExactMfbPokeballPrice({...c,localId:'999'},'Normal','MFB Poké Ball')!==null)fail(id+' wrong localId accepted');
  out[id]=Number(ok.idProduct);
}
if(tcgdexExactMfbPokeballPrice(fixtures['mfb-9'],'Normal','MFB Poké Ball')!==null)fail('mfb-9 contaminated special row accepted');
process.stdout.write(JSON.stringify(out));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(fixtures,ensure_ascii=False),json.dumps(MFB_POKEBALL_EXACT_ROWS)],text=True))


def runtime_legacy_checklist_regression():
    source=INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker=re.search(rf"\bfunction\s+{re.escape(name)}\s*\(",source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{",marker.end());depth=0;quote=None;esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'",'"',chr(96)): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    fixtures={};errors={};cache=Path(tempfile.gettempdir())/"cardoryx_legacy_checklist_v1"
    for card_id in LEGACY_CHECKLIST_PRODUCTS:
        value,error=live_card(card_id,cache)
        if value: fixtures[card_id]=value
        if error: errors[card_id]=error
    if errors or len(fixtures)!=len(LEGACY_CHECKLIST_PRODUCTS): raise AssertionError(f"Legacy checklist live regression unavailable: {errors}")
    start=source.index("const VERIFIED_LEGACY_CHECKLIST_PRODUCTS=")
    end=source.index("const VERIFIED_VARIANT_PRICES =",start)
    registry=source[start:end]
    names=("normText","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel","cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails")
    js="\n".join(extract_fn(n) for n in names)+"\n"+registry
    harness=r"""
const fs=require('fs');
const fixtures=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const rules=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
function fail(m){throw new Error(m)}
const out={};
for(const [id,r] of Object.entries(rules)){
  const [setId,localId,name,finish,pid,sourcePid,exp,pairId]=r,c=fixtures[id];
  const ok=verifiedLegacyChecklistCardmarketPrice(c,finish);
  if(!ok||Number(ok.idProduct)!==Number(pid))fail(id+' exact product mismatch');
  if(!(Number(ok.trend)>0||Number(ok.avg7)>0||Number(ok.avg30)>0))fail(id+' missing exact price');
  if(verifiedLegacyChecklistCardmarketPrice(c,finish==='Holo'?'Normal':'Holo')!==null)fail(id+' wrong finish accepted');
  for(const mutated of [{...c,localId:'999'},{...c,name:name+' wrong'},{...c,set:{...(c.set||{}),id:setId+'x'}}]) if(verifiedLegacyChecklistCardmarketPrice(mutated,finish)!==null)fail(id+' wrong identity accepted');
  const pair=rules[pairId];
  if(!pair||pair[0]!==setId||pair[2]!==name||pair[3]===finish||pair[7]!==id)fail(id+' pair registry invalid');
  const sourceRows=(c.variants_detailed||[]).filter(x=>Number(x?.thirdParty?.cardmarket||0)===Number(sourcePid));
  if(!sourceRows.length)fail(id+' source product evidence missing');
  if(Number(pid)!==Number(sourcePid)){
    const exactLive=(c.variants_detailed||[]).some(x=>Number(x?.thirdParty?.cardmarket||0)===Number(pid));
    if(exactLive)fail(id+' alternate product unexpectedly supplied by TCGdex');
  }
  out[id]={productId:ok.idProduct,sourceProduct:sourcePid,finish,trend:ok.trend};
}
process.stdout.write(JSON.stringify(out));
"""
    fixture_path=Path(tempfile.gettempdir())/"cardoryx_legacy_checklist_fixtures.json"
    rules_path=Path(tempfile.gettempdir())/"cardoryx_legacy_checklist_rules.json"
    fixture_path.write_text(json.dumps(fixtures,ensure_ascii=False),encoding="utf-8")
    rules_path.write_text(json.dumps(LEGACY_CHECKLIST_PRODUCTS,ensure_ascii=False),encoding="utf-8")
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,str(fixture_path),str(rules_path)],text=True))



def main():
    args = cli()
    runtime_regression = runtime_cardmarket_regression()
    runtime_regression["svpSetLogoStaff"] = runtime_svp_set_logo_staff_regression()
    runtime_regression["mepSetLogoStaff"] = runtime_mep_set_logo_staff_regression()
    runtime_regression["ex5BeldumGymChallenge"] = runtime_ex5_beldum_gym_challenge_regression()
    runtime_regression["swsh028GameStop"] = runtime_swsh028_gamestop_regression()
    runtime_regression["mfbPokeball"] = runtime_mfb_pokeball_regression()
    runtime_regression["legacyChecklistProducts"] = runtime_legacy_checklist_regression()
    if args.runtime_only:
        print(json.dumps(runtime_regression, ensure_ascii=False, indent=2))
        return
    dirty = []
    for line in git("status", "--porcelain").splitlines():
        path = line.lstrip(" ?MADRCU").strip()
        if path not in {"index.html", "scripts/test_card_identity_cardmarket_audit.py", "artifacts/card_identity_cardmarket_audit_report.json",
                        "scripts/test_variant_finish_audit.py", "artifacts/variant_finish_audit_report.json"}:
            dirty.append(path)
    if dirty:
        raise SystemExit(f"Unrelated worktree changes present: {dirty}")
    products_path = download_if_needed(args.products, "products_singles_6.json")
    prices_path = download_if_needed(args.prices, "price_guide_6.json")
    cards, parse_errors, snapshot_sha = load_snapshot(args.tcgdex_db)
    by_id = {card["id"]: card for card in cards}

    variant_report = json.loads(VARIANT_REPORT.read_text(encoding="utf-8"))
    expected_historical = int((variant_report.get("summary") or {}).get("identitiesAnalyzed") or 4252)
    historical_ids = {row.get("tcgdexId") for row in (variant_report.get("cards") or []) if row.get("tcgdexId")}
    if len(historical_ids) != expected_historical:
        historical_ids = {card["id"] for card in cards[:expected_historical]}
        historical_note = "Il report Variant & Finish non persiste tutti gli ID: la metrica separata 4.252 usa una slice deterministica di pari dimensione; le conclusioni usano il catalogo completo."
    else:
        historical_note = "ID esatti recuperati dal report Variant & Finish."

    historical_current = {row["tcgdexId"]: row.get("cardmarketIdProduct") for row in (variant_report.get("cards") or [])}
    product_root = json.loads(products_path.read_text(encoding="utf-8"))
    price_root = json.loads(prices_path.read_text(encoding="utf-8"))
    products = {int(row["idProduct"]): row for row in rows(product_root, ("products",)) if row.get("idProduct")}
    prices = {int(row["idProduct"]): row for row in rows(price_root, ("priceGuides", "priceGuide")) if row.get("idProduct")}

    pid_to_cards, multi_ids = defaultdict(set), set()
    for card in cards:
        ids = product_ids(card)
        if len(ids) > 1:
            multi_ids.add(card["id"])
        for pid in ids:
            pid_to_cards[pid].add(card["id"])
    shared_pids = {pid: ids for pid, ids in pid_to_cards.items() if len(ids) > 1}
    shared_identity_ids = set().union(*shared_pids.values()) if shared_pids else set()
    candidate_ids = multi_ids | shared_identity_ids | {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE

    # The historical report already persists the exact top-level product read
    # from TCGdex for all 4,252 identities. Only multi-product identities outside
    # that sample require live detail calls; a single-product shared identity has
    # an unambiguous top-level candidate by construction.
    # Shared-product ambiguity is only actionable when current live TCGdex can
    # prove the top-level Cardmarket product against an exact physical base row.
    # Fetch shared identities as evidence; failed/missing live evidence remains
    # fail-closed and cannot downgrade a P1.
    # Exact set-logo/staff evidence requires live rows even when the identity
    # belongs to the historical sample and is not a shared product. Scope this
    # extra fetch strictly to the two promo sets whose taxonomy is verified.
    verified_set_logo_ids = {
        card["id"] for card in cards
        if card["id"].startswith(("svp-", "mep-")) and any(
            "set-logo" in {str(v or "").strip().lower() for v in (row.get("stamp") or [])}
            for row in (card.get("variants_detailed") or [])
        )
    }
    live_targets = ((multi_ids - historical_ids) | shared_identity_ids | verified_set_logo_ids | {"swshp-SWSH028", "ex5-29"} |
                    set(CONFIRMED_BASE_PRODUCT_CONFLICTS) | set(VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS) |
                    set(VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS) | set(VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS) |
                    set(VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS) | set(MFB_POKEBALL_EXACT_ROWS) |
                    {"sv09-055", "me01-073"} |
                    {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE)
    live, live_errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(live_card, card_id, args.cache): card_id for card_id in sorted(live_targets)}
        for future in concurrent.futures.as_completed(futures):
            card_id = futures[future]
            value, error = future.result()
            if value:
                live[card_id] = value
            if error:
                live_errors[card_id] = error

    source = INDEX.read_text(encoding="utf-8")
    base_overrides = extract_js_object(source, "VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES")
    mcd2019_pairs = extract_js_object(source, "VERIFIED_MCDONALDS_2019_CARDMARKET_PRODUCTS")
    if base_overrides != EXPECTED_BASE_OVERRIDES:
        raise AssertionError("Base Cardmarket override registry differs from the audited P0 identities")
    for forbidden in ("cel25cc-cc020", "cel25cc-cc021"):
        if forbidden in base_overrides:
            raise AssertionError(f"Celebrations Classic must not use base override: {forbidden}")
    if len(mcd2019_pairs) != 39:
        raise AssertionError("McDonald's Collection 2019 registry must contain exactly 39 audited identities")
    play_index = json.loads(PLAY_INDEX.read_text(encoding="utf-8"))
    torkoal_guard = "knownCardmarketIdentityConflict" in source and "sm12-29" in source and "398524" in source
    protected_reverse = {card_id: card_id in source for card_id in sorted(PROTECTED_REVERSE)}
    cases = []
    for card_id in sorted(candidate_ids):
        card = by_id.get(card_id)
        if not card:
            continue
        details, ids = descriptor_map(card), product_ids(card)
        current_cm = (((live.get(card_id) or {}).get("pricing") or {}).get("cardmarket") or {})
        try:
            current_pid = int(current_cm.get("idProduct") or current_cm.get("id_product"))
        except (TypeError, ValueError):
            try:
                current_pid = int(historical_current.get(card_id))
            except (TypeError, ValueError):
                current_pid = ids[0] if len(ids) == 1 else None
        # TCGdex currently points Piplup CEC54 at the Character Rare CEC239
        # product. Cardmarket's official catalogue proves that product 407919
        # is the same-expansion/same-metacard CEC54 base product. Keep both IDs
        # in the audit even when the snapshot omits one of the physical rows.
        if card_id == "sm12-54":
            ids = sorted(set(ids) | {398504, 407919})
            details = dict(details)
            details[398504] = [{"identity": "CEC239 Character Rare", "source": "Cardmarket official catalogue"}]
            details[407919] = [{"identity": "CEC54 base Normal/Reverse", "source": "Cardmarket official catalogue"}]
        base_ids = sorted({cm_id(row) for row in (card.get("variants_detailed") or []) if cm_id(row) and is_base_row(row)})
        alt_ids = sorted(set(ids) - ({current_pid} if current_pid else set()))
        shared = sorted({other for pid in ids for other in pid_to_cards[pid] if other != card_id})

        # Preserve already-proven alternate Play! products before considering
        # live evidence. The live rule is allowed to clear only P1 ambiguity;
        # it must never flatten an EXACT_ALTERNATE_PRODUCT into generic SAFE.
        snapshot_play_rows = (play_index.get("byBaseProduct") or {}).get(str(current_pid), {}) if current_pid else {}
        snapshot_mapped_play_products = {
            int(row["idProduct"])
            for series in snapshot_play_rows.values()
            for row in series
            if row.get("idProduct")
        }
        snapshot_exact_alternate_product = bool(
            current_pid and len(ids) > 1 and
            (set(ids) - set(base_ids)) and
            snapshot_mapped_play_products.intersection(set(ids) - set(base_ids))
        )

        # Strict live evidence can clear stale snapshot ambiguity only when all
        # identity signals agree on the same physical base product. Special
        # stamp/foil/1st Edition rows never qualify and a reused product stays P1.
        live_card_detail = live.get(card_id) or {}
        live_cm = ((live_card_detail.get("pricing") or {}).get("cardmarket") or {})
        try:
            live_pid = int(live_cm.get("idProduct") or live_cm.get("id_product"))
        except (TypeError, ValueError):
            live_pid = None
        live_base_rows = []
        live_explicit_rows = []
        for live_row in live_card_detail.get("variants_detailed") or []:
            pid = cm_id(live_row)
            pricing_cm = ((live_row.get("pricing") or {}).get("cardmarket") or {})
            try:
                pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
            except (TypeError, ValueError):
                pricing_pid = None
            if is_base_row(live_row):
                if pid == live_pid and pricing_pid == live_pid:
                    live_base_rows.append(live_row)
            elif pid == live_pid:
                live_explicit_rows.append(live_row)
        live_usable_price = any(
            isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0
            for key in ("trend", "avg7", "avg30", "avg", "low")
        )
        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        # Cardoryx production supports an exact dynamic resolver only for the
        # verified SVP/MEP `set-logo` taxonomy. A plain Set Stamp row must
        # exclude `staff`; Staff must contain both tokens. Each row must carry
        # its own matching Cardmarket product + live Price Guide.
        live_svp_set_logo_pair = False
        live_svp_stamp_products = {}
        if card_id.startswith(("svp-", "mep-")):
            def exact_svp_stamp_rows(require_staff):
                exact = []
                for row in live_card_detail.get("variants_detailed") or []:
                    stamp_tokens = {str(v or "").strip().lower() for v in (row.get("stamp") or [])}
                    if "set-logo" not in stamp_tokens:
                        continue
                    if ("staff" in stamp_tokens) != require_staff:
                        continue
                    languages = row.get("languages")
                    if isinstance(languages, list) and languages and "it" not in languages:
                        continue
                    row_type = str(row.get("type") or "").strip().lower()
                    row_foil = str(row.get("foil") or "").strip().lower()
                    supported_finish = (
                        (row_type in {"normal", "holo", "reverse"} and not row_foil) or
                        (row_type == "holo" and row_foil == "cosmos") or
                        (row_type == "reverse" and row_foil in {"pokeball", "masterball"})
                    )
                    if not supported_finish:
                        continue
                    row_pid = cm_id(row)
                    pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                    try:
                        pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                    except (TypeError, ValueError):
                        pricing_pid = None
                    usable = any(
                        isinstance(pricing_cm.get(key), (int, float)) and pricing_cm.get(key) > 0
                        for key in ("trend", "avg7", "avg30", "avg", "low")
                    )
                    if row_pid and pricing_pid == row_pid and usable:
                        exact.append((row, row_pid))
                return exact

            svp_set_rows = exact_svp_stamp_rows(False)
            svp_staff_rows = exact_svp_stamp_rows(True)
            if (len(svp_set_rows) == 1 and len(svp_staff_rows) == 1 and
                    svp_set_rows[0][1] != svp_staff_rows[0][1]):
                live_svp_set_logo_pair = True
                live_svp_stamp_products = {
                    "setStamp": svp_set_rows[0][1],
                    "staff": svp_staff_rows[0][1],
                }

        live_ex5_beldum_gym_pair = False
        live_ex5_beldum_products = None
        if card_id == "ex5-29":
            base_rows = []
            gym_rows = []
            for row in live_card_detail.get("variants_detailed") or []:
                stamp_tokens = [str(v or "").strip().lower() for v in (row.get("stamp") or [])]
                row_pid = cm_id(row)
                pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                try:
                    pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                except (TypeError, ValueError):
                    pricing_pid = None
                usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0
                             for k in ("trend", "avg7", "avg30", "avg", "low"))
                if not stamp_tokens and row_pid == 276103 and pricing_pid == 276103 and usable:
                    base_rows.append(row)
                if (stamp_tokens == ["gym-challenge"] and str(row.get("type") or "").lower() == "normal" and
                        not row.get("foil") and row_pid == 280585 and pricing_pid == 280585 and usable):
                    gym_rows.append(row)
            if len(base_rows) == 1 and len(gym_rows) == 1:
                live_ex5_beldum_gym_pair = True
                live_ex5_beldum_products = {"base": 276103, "gymChallenge": 280585}

        live_swsh028_gamestop = False
        live_swsh028_gamestop_pid = None
        if card_id == "swshp-SWSH028":
            exact_rows = []
            for row in live_card_detail.get("variants_detailed") or []:
                stamp_tokens = [str(v or "").strip().lower() for v in (row.get("stamp") or [])]
                row_pid = cm_id(row)
                pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                try:
                    pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                except (TypeError, ValueError):
                    pricing_pid = None
                usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0
                             for k in ("trend", "avg7", "avg30", "avg", "low"))
                if (stamp_tokens == ["gamestop"] and str(row.get("type") or "").lower() == "holo" and
                        not row.get("foil") and row_pid == 742039 and pricing_pid == 742039 and usable):
                    exact_rows.append(row)
            if len(exact_rows) == 1:
                live_swsh028_gamestop = True
                live_swsh028_gamestop_pid = 742039

        exact_mfb_pokeball_pair = False
        exact_mfb_pokeball_products = None
        if card_id in MFB_POKEBALL_EXACT_ROWS:
            rule=MFB_POKEBALL_EXACT_ROWS[card_id]
            identity_ok=bool((card.get("set") or {}).get("id")==rule["setId"] and norm_local(card.get("localId"))==norm_local(rule["localId"]) and card_identity(card).get("name")==rule["name"])
            def exact_mfb_row(expected_pid, expected_stamps):
                matched=[]
                for row in live_card_detail.get("variants_detailed") or []:
                    stamps=row.get("stamp") or []
                    if isinstance(stamps,str): stamps=[stamps]
                    cm=((row.get("pricing") or {}).get("cardmarket") or {})
                    try: ppid=int(cm.get("idProduct") or cm.get("id_product"))
                    except (TypeError,ValueError): ppid=None
                    usable=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ("trend","avg7","avg30","avg","low"))
                    if (cm_id(row)==expected_pid and ppid==expected_pid and usable and str(row.get("type") or "").lower()=="normal" and not row.get("foil") and sorted(map(str,stamps))==sorted(expected_stamps) and str(row.get("size") or "standard").lower()=="standard"):
                        matched.append(row)
                return matched
            base_rows=exact_mfb_row(rule["base"],[rule["deckToken"]])
            pokeball_rows=exact_mfb_row(rule["pokeball"],[rule["deckToken"],"pokeball"])
            pb,pp=products.get(rule["base"]),products.get(rule["pokeball"])
            gb,gp=prices.get(rule["base"]),prices.get(rule["pokeball"])
            catalogue_ok=bool(pb and pp and pb.get("idExpansion")==pp.get("idExpansion")==5526 and pb.get("idMetacard")==pp.get("idMetacard") and pb.get("name")==pp.get("name"))
            guides_ok=bool(gb and gp and int(gb.get("idProduct") or 0)==rule["base"] and int(gp.get("idProduct") or 0)==rule["pokeball"])
            exact_mfb_pokeball_pair=bool(identity_ok and current_pid==rule["base"] and set(ids)=={rule["base"],rule["pokeball"]} and len(base_rows)==1 and len(pokeball_rows)==1 and catalogue_ok and guides_ok)
            if exact_mfb_pokeball_pair:
                exact_mfb_pokeball_products={"base":rule["base"],"pokeball":rule["pokeball"]}

        exact_primary_worlds_pair = False
        exact_primary_worlds_products = None
        if card_id in VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS:
            rule=VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS[card_id]
            identity_ok=bool((card.get("set") or {}).get("id")==rule["setId"] and norm_local(card.get("localId"))==norm_local(rule["localId"]) and card_identity(card).get("name")==rule["name"])
            def exact_worlds_row(expected_pid, expected_stamps):
                matched=[]
                for row in live_card_detail.get("variants_detailed") or []:
                    stamps=row.get("stamp") or []
                    if isinstance(stamps,str): stamps=[stamps]
                    cm=((row.get("pricing") or {}).get("cardmarket") or {})
                    try: ppid=int(cm.get("idProduct") or cm.get("id_product"))
                    except (TypeError,ValueError): ppid=None
                    usable=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ("trend","avg7","avg30","avg","low"))
                    if cm_id(row)==expected_pid and ppid==expected_pid and usable and str(row.get("type") or "").lower()=="normal" and not row.get("foil") and sorted(map(str,stamps))==sorted(expected_stamps) and str(row.get("size") or "standard").lower()=="standard": matched.append(row)
                return matched
            base_rows=exact_worlds_row(rule["productId"],[rule["stamp"]])
            staff_rows=exact_worlds_row(rule["staffProductId"],[rule["stamp"],"staff"])
            exact_primary_worlds_pair=bool(identity_ok and current_pid==rule["productId"] and len(base_rows)==1 and len(staff_rows)==1 and prices.get(rule["productId"]) and prices.get(rule["staffProductId"]))
            if exact_primary_worlds_pair: exact_primary_worlds_products={"base":rule["productId"],"staff":rule["staffProductId"]}

        exact_primary_special_pair = False
        exact_primary_special_products = None
        if card_id in VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS:
            rule = VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS[card_id]
            identity_ok = bool(
                (card.get("set") or {}).get("id") == rule["setId"] and
                norm_local(card.get("localId")) == norm_local(rule["localId"]) and
                card_identity(card).get("name") == rule["name"]
            )
            def exact_special_row(pid, row_type, foil, stamp):
                matches=[]
                for row in live_card_detail.get("variants_detailed") or []:
                    row_stamp=row.get("stamp") or []
                    if isinstance(row_stamp,str): row_stamp=[row_stamp]
                    pricing_cm=((row.get("pricing") or {}).get("cardmarket") or {})
                    try: pricing_pid=int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                    except (TypeError,ValueError): pricing_pid=None
                    usable=any(isinstance(pricing_cm.get(k),(int,float)) and pricing_cm.get(k)>0 for k in ("trend","avg7","avg30","avg","low"))
                    if (cm_id(row)==pid and pricing_pid==pid and usable and
                        str(row.get("type") or "").strip().lower()==row_type and
                        str(row.get("foil") or "").strip().lower()==foil and
                        sorted(map(str,row_stamp))==sorted(map(str,stamp)) and
                        str(row.get("size") or "standard").strip().lower()=="standard"):
                        matches.append(row)
                return matches
            primary_rows=exact_special_row(rule["primary"],rule["primaryType"],rule["primaryFoil"],rule["primaryStamp"])
            alternate_rows=exact_special_row(rule["alternate"],rule["alternateType"],rule["alternateFoil"],rule["alternateStamp"])
            pp,pa=products.get(rule["primary"]),products.get(rule["alternate"])
            gp,ga=prices.get(rule["primary"]),prices.get(rule["alternate"])
            catalogue_ok=bool(pp and pa and pp.get("idMetacard")==pa.get("idMetacard") and pp.get("name")==pa.get("name"))
            guides_ok=bool(gp and ga and int(gp.get("idProduct") or 0)==rule["primary"] and int(ga.get("idProduct") or 0)==rule["alternate"])
            exact_primary_special_pair=bool(
                identity_ok and current_pid==rule["primary"] and set(ids)=={rule["primary"],rule["alternate"]} and
                len(primary_rows)==1 and len(alternate_rows)==1 and catalogue_ok and guides_ok
            )
            if exact_primary_special_pair:
                exact_primary_special_products={"primary":rule["primary"],"alternate":rule["alternate"]}

        exact_standard_jumbo_pair = False
        exact_standard_jumbo_products = None
        if card_id in VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS:
            rule = VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS[card_id]
            ps, pj = products.get(rule["standard"]), products.get(rule["jumbo"])
            gs, gj = prices.get(rule["standard"]), prices.get(rule["jumbo"])
            identity_ok = bool(
                (card.get("set") or {}).get("id") == rule["setId"] and
                norm_local(card.get("localId")) == norm_local(rule["localId"]) and
                card_identity(card).get("name") == rule["name"]
            )
            catalog_ok = bool(
                ps and pj and ps.get("idExpansion") == rule["expansion"] and pj.get("idExpansion") == rule["expansion"] and
                ps.get("idMetacard") == rule["metacard"] and pj.get("idMetacard") == rule["metacard"] and
                ps.get("name") == pj.get("name")
            )
            expected_stamp = sorted(rule.get("stamp") or [])
            def exact_live_size_rows(expected_pid, expected_size):
                matched = []
                for row in live_card_detail.get("variants_detailed") or []:
                    if cm_id(row) != expected_pid:
                        continue
                    if str(row.get("size") or ("standard" if expected_size == "standard" else "")).strip().lower() != expected_size:
                        continue
                    stamps = row.get("stamp") or []
                    if isinstance(stamps, str):
                        stamps = [stamps]
                    if sorted(map(str, stamps)) != expected_stamp:
                        continue
                    pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                    try:
                        pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                    except (TypeError, ValueError):
                        pricing_pid = None
                    usable = any(
                        isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0
                        for k in ("trend", "avg7", "avg30", "avg", "low")
                    )
                    if pricing_pid == expected_pid and usable:
                        matched.append(row)
                return matched

            standard_rows = exact_live_size_rows(rule["standard"], "standard")
            jumbo_rows = exact_live_size_rows(rule["jumbo"], "jumbo")
            rows_ok = bool(len(standard_rows) == 1 and len(jumbo_rows) == 1 and
                           standard_rows[0].get("type") == jumbo_rows[0].get("type"))
            guides_ok = bool(
                gs and gj and int(gs.get("idProduct") or 0) == rule["standard"] and int(gj.get("idProduct") or 0) == rule["jumbo"] and
                any(isinstance(gs.get(k), (int, float)) and gs.get(k) > 0 for k in ("trend", "avg7", "avg30", "avg", "low")) and
                any(isinstance(gj.get(k), (int, float)) and gj.get(k) > 0 for k in ("trend", "avg7", "avg30", "avg", "low"))
            )
            exact_standard_jumbo_pair = bool(
                identity_ok and current_pid == rule["standard"] and set(ids) == {rule["standard"], rule["jumbo"]} and
                catalog_ok and rows_ok and guides_ok
            )
            if exact_standard_jumbo_pair:
                exact_standard_jumbo_products = {"standard": rule["standard"], "jumbo": rule["jumbo"]}

        live_dual_base_pair = False
        if card_id in VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS:
            rule = VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS[card_id]
            expected = {"normal": rule["normal"], "holo": rule["holo"], "reverse": rule["reverse"]}
            exact_rows = {}
            for finish, expected_pid in expected.items():
                matches = []
                for row in live_card_detail.get("variants_detailed") or []:
                    if str(row.get("type") or "").strip().lower() != finish:
                        continue
                    if row.get("stamp") or row.get("foil") or row.get("firstEdition"):
                        continue
                    if str(row.get("size") or "standard").strip().lower() not in {"", "standard"}:
                        continue
                    row_pid = cm_id(row)
                    pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                    try:
                        pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                    except (TypeError, ValueError):
                        pricing_pid = None
                    keys = ("trend-holo", "avg7-holo", "avg30-holo", "avg-holo", "low-holo") if finish == "reverse" else ("trend", "avg7", "avg30", "avg", "low")
                    usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0 for k in keys)
                    if row_pid == expected_pid and pricing_pid == expected_pid and usable:
                        matches.append(row)
                exact_rows[finish] = matches
            pn, ph = products.get(rule["normal"]), products.get(rule["holo"])
            gn, gh = prices.get(rule["normal"]), prices.get(rule["holo"])
            same_identity = bool(
                pn and ph and pn.get("idExpansion") == rule["expansion"] and ph.get("idExpansion") == rule["expansion"] and
                pn.get("idMetacard") == rule["metacard"] and ph.get("idMetacard") == rule["metacard"] and
                pn.get("name") == ph.get("name") and str(pn.get("name") or "").split(" [", 1)[0] == rule["name"]
            )
            guides_ok = bool(gn and gh and int(gn.get("idProduct") or 0) == rule["normal"] and int(gh.get("idProduct") or 0) == rule["holo"])
            live_dual_base_pair = bool(
                current_pid == rule["holo"] and rule["normal"] != rule["holo"] and
                all(len(exact_rows[k]) == 1 for k in ("normal", "holo", "reverse")) and same_identity and guides_ok
            )

        classification, priority, confidence = "SAFE", None, "HIGH"
        reason = "Il prodotto corrente è associato a una riga base e le alternative restano identità fisiche esplicite."
        action = "Nessuna modifica."
        inversion = CONFIRMED_BASE_PRODUCT_CONFLICTS.get(card_id)
        applied_override = False
        resolved_pid = current_pid
        resolved_value = current_value = (prices.get(current_pid) or {}).get("trend") if current_pid else current_cm.get("trend")
        override_tests = None
        if inversion and current_pid == inversion["alternate"]:
            rule = base_overrides.get(card_id)
            applied_override = override_matches(rule, card_id, (card.get("set") or {}).get("id"), card.get("localId"), current_pid)
            exact_live_rows = [row for row in (live.get(card_id) or {}).get("variants_detailed") or []
                               if int((row.get("thirdParty") or {}).get("cardmarket") or 0) == inversion["base"] and
                               int((((row.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)) == inversion["base"]]
            exact_cm = (((exact_live_rows[0].get("pricing") or {}).get("cardmarket") or {}) if exact_live_rows else {})
            override_tests = {
                "exactIdentityAccepted": applied_override,
                "wrongTcgdexIdRejected": not override_matches(rule, card_id + "-other", (card.get("set") or {}).get("id"), card.get("localId"), current_pid),
                "wrongSetIdRejected": not override_matches(rule, card_id, f"{(card.get('set') or {}).get('id')}-other", card.get("localId"), current_pid),
                "wrongLocalIdRejected": not override_matches(rule, card_id, (card.get("set") or {}).get("id"), str(card.get("localId")) + "9", current_pid),
                "correctedFutureProductRejected": not override_matches(rule, card_id, (card.get("set") or {}).get("id"), card.get("localId"), inversion["base"]),
                "exactLivePriceRowPresent": bool(exact_cm),
            }
            if applied_override:
                resolved_pid = inversion["base"]
                resolved_value = next((exact_cm.get(key) for key in ("trend", "avg7", "avg30", "avg", "low")
                                       if isinstance(exact_cm.get(key), (int, float)) and exact_cm.get(key) > 0), None)
                if resolved_value is None:
                    official_guide = prices.get(inversion["base"]) or {}
                    resolved_value = next((official_guide.get(key) for key in ("trend", "avg7", "avg30", "avg", "low")
                                           if isinstance(official_guide.get(key), (int, float)) and official_guide.get(key) > 0), None)
                classification, priority = "SAFE", None
                if exact_cm:
                    reason = "Il resolver applica il prodotto base verificato solo alla quadrupla identità esatta e legge la Price Guide dalla riga live esatta."
                elif resolved_value is not None:
                    reason = "Il resolver applica il prodotto esatto solo alla quadrupla identità verificata e usa la Price Guide ufficiale congelata per quel productId."
                else:
                    reason = "La quadrupla identità esatta blocca il prodotto conflittuale; la Price Guide del prodotto base non è presente nella riga live e il resolver resta fail-closed."
                action = "Mantenere la guardia bidirezionale esatta; nessuna euristica o condivisione cross-identità."
            else:
                classification, priority = "P0_WRONG_PRODUCT", "P0"
                reason = "Il conflitto di prodotto è dimostrato ma la guardia esatta non è disponibile."
                action = "Fail-closed; non usare il prodotto conflittuale."
        elif card_id == "sm12-29" and current_pid == 398524:
            classification, priority = "SOURCE_CONFLICT", "P0_PROTECTED"
            reason, action = "TCGdex assegna il prodotto 398524 a un'altra identità fisica; Cardoryx lo blocca già con guardia esatta.", "Mantenere il fail-closed esistente."
        elif card_id in PROTECTED_REVERSE:
            classification, priority = "SOURCE_CONFLICT", "P0_PROTECTED"
            reason, action = "Conflitto Reverse Cardmarket noto e già protetto con identità/prodotto esatti.", "Mantenere il fail-closed esistente."
        elif card_id in mcd2019_pairs:
            rule = mcd2019_pairs[card_id]
            normal, holo = rule.get("normal") or {}, rule.get("holo") or {}
            pn, ph = products.get(int(normal.get("idProduct") or 0)), products.get(int(holo.get("idProduct") or 0))
            gn, gh = prices.get(int(normal.get("idProduct") or 0)), prices.get(int(holo.get("idProduct") or 0))
            same_meta = bool(pn and ph and pn.get("idExpansion") == 3354 and ph.get("idExpansion") == 3354 and
                             pn.get("idMetacard") == ph.get("idMetacard") and pn.get("idMetacard") is not None)
            exact_names = bool(pn and ph and pn.get("name") == ph.get("name") and
                               norm_local(card.get("localId")) == norm_local(rule.get("localId")))
            exact_rows = bool(
                set(ids) == {int(normal.get("idProduct") or 0), int(holo.get("idProduct") or 0)} and
                any(v.get("finish") == "normal" for v in details.get(int(normal.get("idProduct") or 0), [])) and
                any(v.get("finish") == "holo" for v in details.get(int(holo.get("idProduct") or 0), []))
            )
            priced = bool(gn and gh and isinstance(gn.get("trend"), (int, float)) and gn.get("trend") > 0 and
                          isinstance(gh.get("trend"), (int, float)) and gh.get("trend") > 0)
            # Cardmarket prices are mutable market observations. Identity must
            # remain exact when those values move, so this gate compares the
            # independently verified product IDs, not stale numeric prices.
            snapshot_matches = all(
                int((rule.get(finish) or {}).get("idProduct") or 0) == int((guide or {}).get("idProduct") or 0)
                for finish, guide in (("normal", gn or {}), ("holo", gh or {}))
            )
            if same_meta and exact_names and exact_rows and priced and snapshot_matches:
                classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
                resolved_pid = int(normal["idProduct"])
                resolved_value = normal.get("trend")
                reason = ("McDonald's Collection 2019 ha prodotti Cardmarket Normal/Holo distinti, "
                          "verificati nello stesso set e metacard ufficiale; il runtime li separa per "
                          "identità, nome localizzato e finitura esatti.")
                action = "Mantenere le 39 coppie esatte; nessuna formula productId e nessun fallback fra finiture."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason = "La coppia McDonald's 2019 non supera più i controlli catalogo/metacard/righe/prezzo ufficiali."
                action = "Fail-closed e nuova verifica del catalogo Cardmarket."
        elif card_id in MCDONALDS_2021_EXACT_PAIRS:
            rule = MCDONALDS_2021_EXACT_PAIRS[card_id]
            pn, ph = products.get(rule["normal"]), products.get(rule["holo"])
            gn, gh = prices.get(rule["normal"]), prices.get(rule["holo"])
            same_meta = bool(pn and ph and pn.get("idExpansion") == 3738 and ph.get("idExpansion") == 3738 and
                             pn.get("idMetacard") == ph.get("idMetacard") and pn.get("idMetacard") is not None)
            exact_names = bool(pn and ph and str(pn.get("name") or "").split(" [",1)[0] == rule["name"] and
                               str(ph.get("name") or "").split(" [",1)[0] == rule["name"])
            priced = bool(gn and gh and isinstance(gn.get("trend"),(int,float)) and gn.get("trend") > 0 and
                          isinstance(gh.get("trend"),(int,float)) and gh.get("trend") > 0)
            if same_meta and exact_names and priced:
                classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
                resolved_pid = rule["normal"]
                resolved_value = gn.get("trend")
                reason = ("McDonald's Collection 2021 ha prodotti Cardmarket Normal/Holo distinti, verificati "
                          "sullo stesso metacard ufficiale; Cardoryx li risolve per identità e finitura esatte.")
                action = "Mantenere la tabella esatta 25 carte; nessuna formula productId e nessun fallback tra finiture."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason = "La coppia McDonald's 2021 non supera più i controlli catalogo/metacard/prezzo ufficiali."
                action = "Fail-closed e nuova verifica del catalogo Cardmarket."
        elif live_ex5_beldum_gym_pair:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("Beldum EX Hidden Legends 29/101 ha V1 base Cardmarket 276103 e una stampa Gym Challenge "
                      "fisicamente distinta 280585, entrambe verificate sulla stessa identità live. Il runtime "
                      "separa base Normal/Reverse dallo stamp Gym Challenge senza fallback.")
            action = "Mantenere override base ex5-29 e resolver esatto Gym Challenge; nessuna regola generale per altri set."
        elif live_swsh028_gamestop:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("TCGdex live espone la stampa GameStop esatta di Duraludon SWSH028 con productId "
                      "Cardmarket 742039 e Price Guide sulla stessa riga fisica. Il runtime la risolve "
                      "solo per identità, finitura e stamp esatti.")
            action = "Mantenere il resolver esatto SWSH028 GameStop; EB Games e gli altri promo restano fail-closed."
        elif live_svp_set_logo_pair:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("TCGdex live espone una coppia fisica promo esatta e distinta: `set-logo` e "
                      "`set-logo + staff`, ciascuna con il proprio productId e Price Guide Cardmarket. "
                      "Il runtime Cardoryx le risolve separatamente senza fallback tra stamp.")
            action = "Mantenere il resolver set-logo esatto; nessun mapping statico e nessun riuso prezzo fra Set Stamp e Staff."
        elif card_id in LEGACY_CHECKLIST_PRODUCTS:
            owner_set, owner_local, owner_name, owner_finish, owner_product, source_product, expansion_id, pair_id = LEGACY_CHECKLIST_PRODUCTS[card_id]
            catalogue = products.get(owner_product) or {}
            source_catalogue = products.get(source_product) or {}
            guide = prices.get(owner_product) or {}
            identity_ok = bool((card.get("set") or {}).get("id") == owner_set and norm_local(card.get("localId")) == norm_local(owner_local) and card_identity(card).get("name") == owner_name)
            expected_type = "holo" if owner_finish == "Holo" else "normal"
            source_rows=[]
            exact_rows=[]
            for row in live_card_detail.get("variants_detailed") or []:
                stamps=row.get("stamp") or []
                if isinstance(stamps,str): stamps=[stamps]
                cm=((row.get("pricing") or {}).get("cardmarket") or {})
                try: ppid=int(cm.get("idProduct") or cm.get("id_product"))
                except (TypeError,ValueError): ppid=None
                source_foil=str(row.get("foil") or "").strip().lower()
                foil_ok=(not source_foil) or (owner_set=="base3" and source_foil=="galaxy")
                base_ok=(str(row.get("type") or "").lower()==expected_type and foil_ok and str(row.get("size") or "standard").lower()=="standard")
                if base_ok and cm_id(row)==source_product and ppid==source_product: source_rows.append(row)
                if base_ok and cm_id(row)==owner_product and ppid==owner_product: exact_rows.append(row)
            pair=LEGACY_CHECKLIST_PRODUCTS.get(pair_id)
            pair_ok=bool(pair and pair[0]==owner_set and pair[2]==owner_name and pair[3]!=owner_finish and pair[1]!=owner_local and pair[7]==card_id)
            same_meta=bool(catalogue and source_catalogue and int(catalogue.get("idMetacard") or 0)>0 and int(catalogue.get("idMetacard") or 0)==int(source_catalogue.get("idMetacard") or -1))
            catalogue_ok=bool(catalogue and source_catalogue and int(catalogue.get("idExpansion") or 0)==expansion_id and int(source_catalogue.get("idExpansion") or 0)==expansion_id and catalogue.get("name")==source_catalogue.get("name") and same_meta)
            guide_ok=bool(guide and int(guide.get("idProduct") or 0)==owner_product and any(isinstance(guide.get(k),(int,float)) and guide.get(k)>0 for k in ("trend","avg7","avg30","avg","low")))
            source_ok=bool(source_rows and ((owner_product==source_product and exact_rows) or (owner_product!=source_product and not exact_rows)))
            source_guard=("VERIFIED_LEGACY_CHECKLIST_PRODUCTS" in source and "verifiedLegacyChecklistCardmarketPrice" in source)
            if identity_ok and pair_ok and catalogue_ok and guide_ok and source_ok and source_guard:
                classification, priority, confidence = "SAFE", None, "HIGH"
                resolved_pid=owner_product
                resolved_value=next((guide.get(k) for k in ("trend","avg7","avg30","avg","low") if isinstance(guide.get(k),(int,float)) and guide.get(k)>0), None)
                reason=("La checklist fisica ha numeri distinti Holo/Non Holo e il catalogo Cardmarket contiene productId distinti con lo stesso metacard. Cardoryx vincola set, numero, nome e finitura all'idProduct esatto e usa solo i campi standard del Price Guide di quel prodotto.")
                action="Mantenere il mapping esatto per questa sola coppia; nessun riuso del productId della controparte e nessuna inferenza dai campi *-holo."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason="La coppia legacy non supera tutti i gate esatti di checklist, prodotto, metacard, finitura o Price Guide."
                action="Fail-closed; nessun riuso del productId della controparte."
        elif card_id in BATCH2_SHARED_PRODUCT_OWNERS:
            owner_set, owner_local, owner_name, owner_product = BATCH2_SHARED_PRODUCT_OWNERS[card_id]
            catalogue = products.get(owner_product) or {}
            guide = prices.get(owner_product) or {}
            source_guard = "VERIFIED_SHARED_CARDMARKET_PRODUCT_OWNERS" in source
            exact_owner = bool(
                (card.get("set") or {}).get("id") == owner_set and
                norm_local(card.get("localId")) == norm_local(owner_local) and
                card_identity(card).get("name") == owner_name and current_pid == owner_product
            )
            official_evidence = bool(catalogue and guide and isinstance(guide.get("trend"), (int, float)))
            if exact_owner and official_evidence and source_guard:
                classification, priority, confidence = "SAFE", None, "HIGH"
                resolved_pid, resolved_value = owner_product, guide.get("trend")
                reason = ("Il productId condiviso appartiene a questa identità fisica esatta secondo il catalogo "
                          "ufficiale; il runtime ne vieta l'uso a qualsiasi tcgdexId/set/numero/nome diverso.")
                action = "Mantenere la guardia esatta del proprietario; nessun riuso del prodotto condiviso."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason = "La proprietà esatta del productId condiviso non supera più tutti i gate catalogo/runtime."
                action = "Fail-closed e nuova verifica delle fonti ufficiali."
        elif (card_id in EX8_VERIFIED_SHARED_PRODUCT_OWNERS and
              current_pid == EX8_VERIFIED_SHARED_PRODUCT_OWNERS[card_id]["productId"] and
              set(shared) == EX8_VERIFIED_SHARED_PRODUCT_OWNERS[card_id]["blockedTcgdexIds"] and
              "EX Deoxys prodotti checklist verificati" in source):
            classification, priority, confidence = "SAFE", None, "HIGH"
            reason = ("Il prodotto corrente appartiene all'identità checklist esatta; ogni altra identità "
                      "TCGdex che lo riusava è ora protetta da un override Cardmarket esatto e fail-closed.")
            action = "Mantenere le guardie EX Deoxys esatte; nessun riuso del prodotto condiviso."
        elif card_id in MFB_POKEBALL_EXACT_ROWS:
            if exact_mfb_pokeball_pair and "VERIFIED_MFB_POKEBALL_ROWS" in source and "tcgdexExactMfbPokeballPrice" in source and "MFB Poké Ball" in source:
                rule=MFB_POKEBALL_EXACT_ROWS[card_id]
                classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
                resolved_pid=rule["base"]
                resolved_value=(prices.get(rule["base"]) or {}).get("trend")
                reason=("My First Battle espone una stampa regolare e una variante fisica First Pokémon/Starting Energy con bordo blu e simbolo Poké Ball; TCGdex e Cardmarket separano le due righe con productId e Price Guide distinti. Il runtime risolve la variante Poké Ball solo dopo selezione manuale esplicita.")
                action="Mantenere il mapping sulle sole 6 identità verificate; nessuna regola per provenienza mini-mazzo, Potion/Switch o mfb-9."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason="La coppia My First Battle regolare/Poké Ball non supera più tutti i gate fisici e Cardmarket esatti."
                action="Fail-closed; non usare provenienza del mini-mazzo come variante fisica."
        elif card_id in VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS:
            if exact_primary_worlds_pair and "VERIFIED_PRIMARY_WORLDS_STAMPS" in source and "tcgdexExactWorldsStampPrice" in source:
                rule=VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS[card_id]
                classification, priority, confidence = "SAFE", None, "HIGH"
                resolved_pid=rule["productId"]
                resolved_value=(prices.get(rule["productId"]) or {}).get("trend")
                reason="TCGdex live prova la stampa Worlds base top-level e la Staff separata con productId e Price Guide distinti; il runtime usa solo stamp, identità e prodotto esatti."
                action="Mantenere resolver Worlds esatto; piazzamenti senza productId restano fail-closed."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason="La coppia Worlds base/Staff non supera più tutti i gate esatti."
                action="Fail-closed; nessuna euristica Worlds generica."
        elif card_id in VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS:
            if exact_primary_special_pair and "VERIFIED_EXACT_PRIMARY_SPECIAL_CARDMARKET_ROWS" in source:
                rule=VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS[card_id]
                classification, priority, confidence = "SAFE", None, "HIGH"
                resolved_pid=rule["primary"]
                resolved_value=(prices.get(rule["primary"]) or {}).get("trend")
                reason=("TCGdex live separa la stampa primaria non timbrata dalla ristampa/promozionale esplicita; "
                        "entrambe hanno productId e Price Guide propri e il runtime risolve solo la riga fisica primaria esatta.")
                action="Mantenere il resolver esatto per la riga primaria; nessun fallback verso la stampa alternativa."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason="La coppia primaria/promozionale registrata non supera più tutti i gate esatti."
                action="Fail-closed e nuova verifica delle fonti; nessuna euristica di finitura o ristampa."
        elif card_id in VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS:
            if exact_standard_jumbo_pair:
                rule = VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS[card_id]
                classification, priority, confidence = "SAFE", None, "HIGH"
                resolved_pid = rule["standard"]
                resolved_value = (prices.get(rule["standard"]) or {}).get("trend")
                reason = ("TCGdex documenta due formati fisici distinti della stessa promo: una riga Standard e una Jumbo, "
                          "con productId Cardmarket separati. Catalogo ufficiale, set, metacard, nome, stamp e Price Guide "
                          "coincidono; il prodotto top-level corrente è esclusivamente quello Standard.")
                action = "Nessuna modifica runtime: mantenere il prodotto Standard corrente e non trasferire il prezzo alla Jumbo."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason = "La coppia Standard/Jumbo registrata non supera più tutti i gate esatti di identità, formato o Price Guide."
                action = "Fail-closed e nuova verifica delle fonti ufficiali; nessuna euristica Standard/Jumbo."
        elif card_id == "swshp-SWSH163":
            standard, oversized = products.get(572163), products.get(576915)
            exact_oversized_pair = bool(
                current_pid == 572163 and set(ids) == {572163, 576915} and standard and oversized and
                standard.get("name") == "Zacian V-UNION [Union Gain]" and
                oversized.get("name") == "Zacian V-UNION [Oversized]" and
                prices.get(572163) and prices.get(576915)
            )
            if exact_oversized_pair:
                classification, priority, confidence = "SAFE", None, "HIGH"
                reason = ("Il prodotto 572163 è la carta standard SWSH163; 576915 è esplicitamente Oversized "
                          "nel catalogo ufficiale ed è bloccato dal runtime per la carta standard.")
                action = "Mantenere la guardia esatta standard/Oversized; nessun fallback fra formati fisici."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason = "La distinzione standard/Oversized non è più dimostrata dalle fonti ufficiali correnti."
                action = "Fail-closed e nuova verifica del catalogo Cardmarket."
        elif live_dual_base_pair:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            rule = VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS[card_id]
            resolved_pid = rule["holo"]
            resolved_value = (prices.get(rule["holo"]) or {}).get("trend")
            reason = ("TCGdex live espone Normal e Holo/Reverse come prodotti Cardmarket fisicamente distinti; "
                      "il catalogo ufficiale conferma stesso set, stesso metacard e stesso nome. Il runtime "
                      "seleziona il productId esclusivamente dalla finitura esatta e non usa la stampa Player Rewards senza productId.")
            action = "Mantenere il resolver esatto limitato a questa identità; nessuna generalizzazione ad altre carte o tassonomie."
        elif live_exact_base_evidence and not snapshot_exact_alternate_product:
            classification, priority, confidence = "SAFE", None, "HIGH"
            resolved_pid = live_pid
            resolved_value = next(
                (live_cm.get(key) for key in ("trend", "avg7", "avg30", "avg", "low")
                 if isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0),
                None,
            )
            reason = ("TCGdex live conferma lo stesso productId Cardmarket sia a livello top-level sia "
                      "in una riga fisica base unstamped/unfoiled, con prezzo reale disponibile e senza "
                      "riuso dello stesso prodotto da parte di varianti speciali.")
            action = "Nessuna modifica di produzione: identità base live esatta, falso positivo dello snapshot statico."
        elif not current_pid and len(ids) > 1:
            classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
            reason = "La sorgente espone più prodotti ma non un product ID top-level corrente verificabile."
            action = "Restare fail-closed finché il prodotto principale non è dimostrato."
        elif shared and current_pid and current_pid in shared_pids:
            classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "MEDIUM"
            reason = "Lo stesso prodotto corrente è associato da TCGdex a più tcgdexId fisicamente distinti e non esiste una protezione esatta nota."
            action = "Verificare il prodotto sul catalogo Cardmarket; nel frattempo preferire fail-closed."
        elif current_pid and current_pid not in base_ids:
            classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "MEDIUM"
            reason, action = "Il prodotto top-level corrente non compare tra le righe fisiche base unstamped/unfoiled.", "Verifica esatta V1/V2/V3 prima di qualsiasi mapping."
        elif len(ids) > 1:
            if set(ids) - set(base_ids):
                play_rows = (play_index.get("byBaseProduct") or {}).get(str(current_pid), {}) if current_pid else {}
                mapped_play_products = {int(row["idProduct"]) for series in play_rows.values() for row in series if row.get("idProduct")}
                if mapped_play_products.intersection(set(ids) - set(base_ids)):
                    classification, priority = "EXACT_ALTERNATE_PRODUCT", "P2"
                    reason = "Una variante Play! fisicamente distinta possiede un prodotto esatto e Cardoryx la distingue tramite l'indice locale dedicato."
                    action = "Mantenere il mapping esatto esistente."
                else:
                    classification, priority = "SAFE", None
                    reason = "Le alternative appartengono a stamp/foil espliciti; Cardoryx usa il prodotto base corretto e non trasferisce automaticamente quel prezzo alle alternative."
                    action = "Nessuna modifica: mantenere la separazione/fail-closed corrente."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "MEDIUM"
                reason, action = "Più prodotti Cardmarket sono associati a finiture base senza metadati sufficienti a scegliere automaticamente.", "Verifica esatta V1/V2/V3; non generalizzare."

        case = {
            **card_identity(card), "inHistorical4252": card_id in historical_ids,
            "currentProductId": current_pid, "alternateProductIds": alt_ids, "allProductIds": ids,
            "baseRowProductIdsAccordingToTcgdex": base_ids,
            "physicalVariantsByProductId": {str(pid): details[pid] for pid in ids},
            "cardmarketProductCatalog": {str(pid): products.get(pid) for pid in ids},
            "sharedProductWithTcgdexIds": shared, "currentCardoryxValue": current_value,
            "baseOverrideApplied": applied_override, "resolvedProductId": resolved_pid,
            "resolvedCardoryxValue": resolved_value, "baseOverrideGuardTests": override_tests,
            "liveExactBaseEvidence": live_exact_base_evidence,
            "liveExactBaseProductId": live_pid if live_exact_base_evidence else None,
            "liveExactBasePriceAvailable": live_usable_price,
            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
            "liveExactSvpSetLogoStaffPair": live_svp_set_logo_pair,
            "liveExactSvpStampProducts": live_svp_stamp_products,
            "liveExactEx5BeldumGymChallenge": live_ex5_beldum_gym_pair,
            "liveExactEx5BeldumProducts": live_ex5_beldum_products,
            "liveExactSwsh028GameStop": live_swsh028_gamestop,
            "liveExactSwsh028GameStopProductId": live_swsh028_gamestop_pid,
            "verifiedPrimaryWorldsPair": exact_primary_worlds_pair,
            "verifiedPrimaryWorldsProducts": exact_primary_worlds_products,
            "verifiedPrimarySpecialPair": exact_primary_special_pair,
            "verifiedPrimarySpecialProducts": exact_primary_special_products,
            "verifiedStandardJumboPair": exact_standard_jumbo_pair,
            "verifiedStandardJumboProducts": exact_standard_jumbo_products,
            "snapshotExactAlternateProductProtected": snapshot_exact_alternate_product,
            "realPriceGuideValues": {str(pid): price_compact(prices.get(pid)) for pid in ids if prices.get(pid)},
            "trendDeltaVersusCurrent": {str(pid): round(row["trend"] - current_value, 2) for pid, row in prices.items()
                                         if pid in ids and pid != current_pid and isinstance(current_value, (int, float)) and isinstance(row.get("trend"), (int, float))},
            "classification": classification, "priority": priority, "confidence": confidence,
            "reason": reason, "recommendedAction": action,
        }
        if inversion and card_id.startswith("sv08-"):
            case["confirmedCardmarketVersionEvidence"] = {
                "V1ProductId": inversion["base"], "V2ProductId": inversion["alternate"],
                "V1Url": f"https://www.cardmarket.com/en/Pokemon/Products/Singles/Surging-Sparks/{case['name']}-V1-{inversion['cardmarketCode']}",
                "V2Url": f"https://www.cardmarket.com/en/Pokemon/Products/Singles/Surging-Sparks/{case['name']}-V2-{inversion['cardmarketCode']}",
                "physicalVariantAccordingToCardmarket": {
                    str(inversion["base"]): "V1 — stampa base standard; prodotto con slot Normal/Reverse",
                    str(inversion["alternate"]): "V2 — stampa Pokémon Horizons stamped",
                },
                "tcgdexAssociationIsInverted": True,
            }
        if card_id == "sm12-54":
            case["verifiedBaseProductId"] = 407919
            case["currentProductPhysicalIdentity"] = "Piplup CEC239 Character Rare"
            case["verifiedBasePhysicalIdentity"] = "Piplup CEC54 base Normal/Reverse"
            case["verifiedBaseProductConflictEvidence"] = {
                "conflictingProductId": 398504, "baseProductId": 407919,
                "exactIdentity": "Cosmic Eclipse / Eclissi Cosmica 054/236",
                "guard": "tcgdexId + setId + normalized localId + current product",
                "priceSourcePolicy": "required live exact variants_detailed product row; otherwise fail-closed",
                "exactLivePriceRowPresent": bool(exact_cm),
            }
        cases.append(case)

    counts = Counter(case["classification"] for case in cases)
    history_cards = [by_id[x] for x in historical_ids if x in by_id]
    p0 = [case for case in cases if case["classification"] == "P0_WRONG_PRODUCT"]
    p1 = [case for case in cases if case["classification"] == "P1_AMBIGUOUS_PRODUCT"]
    over, under = [], []
    for case in p0 + p1:
        current = case.get("currentCardoryxValue")
        alternatives = [row.get("trend") for key, row in case["realPriceGuideValues"].items()
                        if int(key) != case.get("currentProductId") and row and isinstance(row.get("trend"), (int, float))]
        if isinstance(current, (int, float)) and alternatives:
            if current > min(alternatives): over.append((round(current - min(alternatives), 2), case["tcgdexId"], current, min(alternatives)))
            if current < max(alternatives): under.append((round(max(alternatives) - current, 2), case["tcgdexId"], current, max(alternatives)))

    fuecoco = next(case for case in cases if case["tcgdexId"] == "sv08-029")
    fuecoco_snapshot = by_id["sv08-029"]
    fuecoco_live = live.get("sv08-029") or {}
    fuecoco.update({
        "phase1Classification": "SOURCE_CONFLICT",
        "operationalFinding": "WRONG_BASE_PRODUCT",
        "resolutionClass": "NEEDS_EXACT_MAPPING",
        "tcgdexVariants": fuecoco_snapshot.get("variants"),
        "tcgdexVariantsDetailed": fuecoco_snapshot.get("variants_detailed"),
        "liveTcgdexPricingCardmarket": ((fuecoco_live.get("pricing") or {}).get("cardmarket") or {}),
        "liveTcgdexVariantsDetailed": fuecoco_live.get("variants_detailed"),
        "exactNormalUnstampedProductExists": True,
        "productForDisplayedNormalCard": 794286,
        "correctionPolicy": "Applicabile solo con mapping esatto tcgdexId/setId/localId e guardia sul prodotto conflittuale corrente 794946; altrimenti fail-closed.",
        "generalRuleRisk": "HIGH: V1/V2/V3 non codificano universalmente la stessa relazione fisica e includono 1st Edition, shadowless, promo, stamped e reprint.",
    })
    multi_classifications = Counter(c["classification"] for c in cases if len(c["allProductIds"]) > 1)
    historical_classifications = Counter(c["classification"] for c in cases if c["inHistorical4252"])
    confirmed_over = []
    for case in p0:
        current = case.get("currentCardoryxValue")
        alternatives = [row.get("trend") for key, row in case["realPriceGuideValues"].items()
                        if int(key) != case.get("currentProductId") and row and isinstance(row.get("trend"), (int, float))]
        if isinstance(current, (int, float)) and alternatives and current > min(alternatives):
            confirmed_over.append((round(current - min(alternatives), 2), case["tcgdexId"], current, min(alternatives)))
    known_phase_a_p0 = [case for case in p0 if case["tcgdexId"] in EXPECTED_BASE_OVERRIDES]
    piplup = next(case for case in cases if case["tcgdexId"] == "sm12-54")
    report = {
        "schema": 3, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "auditMode": "PRODUCTION_REGRESSION_PLUS_READ_ONLY_PHASE_B_DIAGNOSTIC",
        "mainSha": git("rev-parse", "HEAD"),
        "snapshot": {"tcgdexGitSha": snapshot_sha, "databasePath": str(args.tcgdex_db), "parseErrors": parse_errors,
                     "sameSnapshotAsVariantAudit": snapshot_sha in json.dumps(variant_report)},
        "sources": {"indexHtmlSha256": sha256(INDEX), "variantReportSha256": sha256(VARIANT_REPORT),
                    "cardmarketPlayIndexSha256": sha256(PLAY_INDEX),
                    "cardmarketProducts": {"path": str(products_path), "sha256": sha256(products_path)},
                    "cardmarketPriceGuide": {"path": str(prices_path), "sha256": sha256(prices_path)}, "liveTcgdexApi": API},
        "coverage": {
            "historical4252": {"expectedIdentities": expected_historical, "recoveredIdentities": len(history_cards), "note": historical_note,
                               "identitiesWithCardmarketProduct": sum(bool(product_ids(c)) for c in history_cards),
                               "identitiesWithOneProduct": sum(len(product_ids(c)) == 1 for c in history_cards),
                               "identitiesWithMultipleProducts": sum(len(product_ids(c)) > 1 for c in history_cards)},
            "fullCatalog": {"identitiesAnalyzed": len(cards), "identitiesWithCardmarketProduct": sum(bool(product_ids(c)) for c in cards),
                            "identitiesWithOneProduct": sum(len(product_ids(c)) == 1 for c in cards),
                            "identitiesWithMultipleProducts": len(multi_ids), "distinctProductsSharedAcrossTcgdexIds": len(shared_pids),
                            "candidateIdentitiesDeepAudited": len(cases), "liveDetailRequests": len(live_targets),
                            "liveApiErrors": live_errors}},
        "classificationTotals": {name: counts.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "liveExactBaseEvidence": {
            "count": sum(bool(case.get("liveExactBaseEvidence")) for case in cases),
            "ids": [case["tcgdexId"] for case in cases if case.get("liveExactBaseEvidence")],
            "protectedExactAlternateCount": sum(bool(case.get("snapshotExactAlternateProductProtected")) for case in cases),
            "policy": "live top-level product == live physical base-row product == live row pricing product; usable real price; no explicit special row reuses product; existing exact alternate Play products remain protected",
        },
        "p0Regression": {"before": 20, "after": len(known_phase_a_p0),
                         "exactOverridesApplied": sum(bool(c.get("baseOverrideApplied")) for c in cases),
                         "registry": base_overrides,
                         "noP1AutoMapped": not any(c.get("baseOverrideApplied") for c in cases if c["tcgdexId"] not in EXPECTED_BASE_OVERRIDES),
                         "priorThree": {"before": 3, "after": sum(c["classification"] == "P0_WRONG_PRODUCT" for c in cases if c["tcgdexId"].startswith("sv08-") and c["tcgdexId"] in EXPECTED_BASE_OVERRIDES)},
                         "piplup": {"before": 1, "after": int(piplup["classification"] == "P0_WRONG_PRODUCT")}},
        "multiProductClassificationTotals": {name: multi_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "historical4252CandidateClassificationTotals": {name: historical_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "fuecoco": fuecoco, "piplup": piplup, "p0WrongProduct": p0,
        "p1AmbiguousProductIds": [c["tcgdexId"] for c in p1],
        "sourceConflicts": [c for c in cases if c["classification"] == "SOURCE_CONFLICT"],
        "unmappedExactProduct": [c for c in cases if c["classification"] == "UNMAPPED_EXACT_PRODUCT"],
        "caseIndex": [{"tcgdexId": c["tcgdexId"], "classification": c["classification"],
                       "priority": c.get("priority"), "inHistorical4252": c["inHistorical4252"]}
                      for c in cases],
        "alreadyProtected": {"torkoalSm12_29Product398524": torkoal_guard, "reverseConflicts": protected_reverse,
                             "allRequestedProtectionsPresent": torkoal_guard and all(protected_reverse.values())},
        "riskExtremes": {"maximumObservedOvervaluation": max(over, default=None), "maximumObservedUndervaluation": max(under, default=None),
                         "maximumConfirmedP0Overvaluation": max(confirmed_over, default=None),
                         "maximumConfirmedP0Undervaluation": None,
                         "method": "Differenze fra soli campi trend reali Cardmarket; nessuna stima o interpolazione."},
        "safety": {"productionFilesModified": True, "indexHtmlModified": True,
                   "productionChangeScope": "20 exact Cardmarket base-product identity overrides; latest batch adds 9 metacard-verified EX Team Magma vs Team Aqua identities",
                   "cardmarketDataModified": False,
                   "retailModified": False, "retailPricesModified": False, "scannerOcrSearchModified": False,
                   "finishesModified": True, "workflowAdded": False, "mergePerformed": False},
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(OUT), "mainSha": report["mainSha"], "snapshot": snapshot_sha,
                      "coverage": report["coverage"], "classifications": report["classificationTotals"],
                      "fuecoco": {k: fuecoco.get(k) for k in ("currentProductId", "alternateProductIds", "currentCardoryxValue", "classification")},
                      "riskExtremes": report["riskExtremes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
