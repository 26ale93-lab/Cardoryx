#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V15
# TEST ISOLATO READ-ONLY
# Legge i campi strutturati WooCommerce/JSON-LD verificati nel V6.
# NON modifica retail_prices.json. NON tocca Cardmarket. NON crea identita.

import json
import re
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://www.centrodelfumetto.it"
SITEMAP_INDEX = BASE + "/sitemap_index.xml"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("centro_fumetto_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/15.0)"
TIMEOUT = 8
MAX_SITEMAPS = 120
MAX_PRODUCTS = 400
MAX_RUNTIME_SECONDS = 840
SLEEP_SECONDS = 0.0
POKEMON_SINGLE_PATH = "/pokemon/pokemon-single/"

# Solo alias di set esplicitamente verificabili tra nomenclatura inglese del negozio
# e nomenclatura italiana gia presente in Cardoryx. In V7 non aggiungiamo alias:
# prima misuriamo esattamente quali set restano fuori.
SET_ALIASES = {
    "brilliant stars": "Astri Lucenti",
    "silver tempest": "Tempesta Argentata",
    "crown zenith": "Zenit Regale",
    "lost origin": "Origine Perduta",
    "fusion strike": "Colpo Fusione",
    "chilling reign": "Regno Glaciale",
    "astral radiance": "Lucentezza Siderale",
    "darkness ablaze": "Fiamme Oscure",
    "evolving skies": "Evoluzioni Eteree",
    "battle styles": "Stili di Lotta",
    "celebrations": "Gran Festa",
    "pokemon tcg pokemon go": "Pokémon GO",
    "pokemon go": "Pokémon GO",
}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "it-IT,it;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,*/*",
        "Connection": "close",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace"), r.geturl(), getattr(r, "status", None)

def sitemap_urls(xml):
    return [unescape(x.strip()) for x in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)]

def plain(html):
    x = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    x = re.sub(r"<style\b.*?</style>", " ", x, flags=re.I | re.S)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", unescape(x)).strip()

def collector_parts(v):
    # Conservativo ma compatibile con numerazioni reali viste nel V6:
    # 2/102, 72/70, TG01, GG16, 065.
    s = str(v or "").strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z]{0,4})(\d{1,4})(?:/([A-Z]{0,4})(\d{1,4}))?", s)
    if not m:
        return None
    return (
        m.group(1) or "",
        int(m.group(2)),
        m.group(3) or "",
        int(m.group(4)) if m.group(4) else None,
    )

def short_number_key(v):
    p = collector_parts(v)
    if not p:
        return None
    # TG01 != 01; GG25 != 25; SWSH123 != 123; SM123 != 123.
    return (p[0], p[1])

def iter_cards(data):
    cards = data.get("cards", {})
    return cards if isinstance(cards, list) else cards.values()

def build_indexes(data):
    exact = defaultdict(list)
    by_set_number_name = defaultdict(list)
    by_set_short_number_name = defaultdict(list)
    known_sets = set()
    for c in iter_cards(data):
        cp = collector_parts(c.get("number"))
        sp = short_number_key(c.get("number"))
        if not cp or not sp:
            continue
        sk = norm(c.get("set"))
        nk = norm(c.get("name"))
        known_sets.add(sk)
        exact[(sk, cp, nk, c.get("variant"))].append(c)
        by_set_number_name[(sk, cp, nk)].append(c)
        by_set_short_number_name[(sk, sp, nk)].append(c)
    return exact, by_set_number_name, by_set_short_number_name, known_sets

def store_count(card):
    return len({
        norm(o.get("store"))
        for o in card.get("offers", [])
        if o.get("store")
    })

def jsonld_objects(html):
    out = []
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.I | re.S
    ):
        raw = unescape(raw).strip()
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        stack = [obj]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                out.append(x)
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    return out

def structured_properties(html):
    props = {}
    product_objs = []
    for obj in jsonld_objects(html):
        typ = obj.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if "Product" in types:
            product_objs.append(obj)
        if obj.get("@type") == "PropertyValue":
            name = str(obj.get("name") or "").strip()
            value = obj.get("value")
            if name and value is not None:
                props[norm(name)] = str(value).strip()
    return props, product_objs

def first_prop(props, *names):
    for name in names:
        v = props.get(norm(name))
        if v:
            return v
    return ""

def product_price_availability(product_objs, html):
    prices = []
    availability = None

    def inspect_offer(x):
        nonlocal availability
        if not isinstance(x, dict):
            return
        p = x.get("price")
        if p is not None:
            try:
                f = float(str(p).replace(",", "."))
                if f > 0:
                    prices.append(f)
            except ValueError:
                pass
        a = str(x.get("availability") or "").lower()
        if "outofstock" in a:
            availability = False
        elif "instock" in a and availability is not False:
            availability = True

    for p in product_objs:
        offers = p.get("offers")
        if isinstance(offers, list):
            for o in offers:
                inspect_offer(o)
        else:
            inspect_offer(offers)

    # Fallback SOLO a meta prodotto specifici, non al primo euro della pagina.
    if not prices:
        for pat in (
            r'property=["\']product:price:amount["\'][^>]*content=["\']([0-9]+(?:[.,][0-9]{1,2})?)',
            r'itemprop=["\']price["\'][^>]*content=["\']([0-9]+(?:[.,][0-9]{1,2})?)',
        ):
            m = re.search(pat, html, re.I)
            if m:
                try:
                    f = float(m.group(1).replace(",", "."))
                    if f > 0:
                        prices.append(f)
                        break
                except ValueError:
                    pass

    # Meta availability verificato nel V6.
    if availability is None:
        if re.search(r'(?:schema\.org/OutOfStock|product:availability["\'][^>]*content=["\']outofstock)', html, re.I):
            availability = False
        elif re.search(r'(?:schema\.org/InStock|product:availability["\'][^>]*content=["\']instock)', html, re.I):
            availability = True

    # Più prezzi diversi = ambiguo, non scegliamo.
    unique = sorted(set(round(x, 2) for x in prices))
    price = unique[0] if len(unique) == 1 else None
    return price, availability, unique

def variant_from_structured(foiling, reverse):
    nf = norm(foiling)
    nr = norm(reverse)

    if nr in {"si", "yes", "true", "1"}:
        return "Reverse Holo", "reverseHolo=yes"

    if "reverse" in nf:
        return "Reverse Holo", "foiling=reverse"

    if "holo" in nf and "reverse" not in nf:
        return "Holo", "foiling=holo"

    # Il V6 ha verificato il valore strutturato "Foiling: Normale".
    # Non usiamo la rarita per dedurre la variante.
    if nf in {"normale", "normal", "non foil", "non holo"} and nr in {"no", "false", "0", ""}:
        return None, "foilingNormaleNotVariantSafe"

    return None, "unconfirmed"

def clean_name(title):
    s = str(title or "").strip()
    s = re.sub(r"\s*[–—-]\s*Near Mint\s*,?\s*Italiano\s*$", "", s, flags=re.I)
    s = re.sub(r"^\s*Carta\s+Pok[eé]mon\s+", "", s, flags=re.I)
    return s.strip()

def parse_page(html, url):
    props, product_objs = structured_properties(html)

    h = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    title = plain(h.group(1)) if h else ""
    if not title:
        for obj in product_objs:
            if obj.get("name"):
                title = str(obj["name"]).strip()
                break

    expansion = first_prop(props, "pa_ct_espansione")
    condition = first_prop(props, "pa_ct_condizione")
    language = first_prop(props, "pa_ct_lingua")
    number = first_prop(props, "pa_ct_numero_collezione")
    rarity = first_prop(props, "pa_ct_rarita")
    foiling = first_prop(props, "pa_ct_foiling")
    reverse = first_prop(props, "pa_ct_reverse_holo")
    first_edition = first_prop(props, "pa_ct_first_edition")

    price, available, price_candidates = product_price_availability(product_objs, html)
    variant, variant_signal = variant_from_structured(foiling, reverse)

    return {
        "url": url,
        "title": title,
        "name": clean_name(title),
        "set": expansion,
        "condition": condition,
        "language": language,
        "number": number,
        "rarity": rarity,
        "foiling": foiling,
        "reverseHolo": reverse,
        "firstEdition": first_edition,
        "variant": variant,
        "variantSignal": variant_signal,
        "price": price,
        "priceCandidates": price_candidates,
        "available": available,
    }

def discover():
    index_xml, _, _ = get(SITEMAP_INDEX)
    sms = [u for u in sitemap_urls(index_xml) if "product-sitemap" in u.lower()]
    direct = BASE + "/product-sitemap.xml"
    if direct not in sms:
        sms.insert(0, direct)

    seen = set()
    urls = []
    smstats = []
    for sm in sms[:MAX_SITEMAPS]:
        try:
            body, final, status = get(sm)
            locs = sitemap_urls(body)
            smstats.append({"url": sm, "finalUrl": final, "status": status, "locs": len(locs)})
            for u in locs:
                if POKEMON_SINGLE_PATH not in u.lower() or u in seen:
                    continue
                seen.add(u)
                urls.append(u)
        except Exception as e:
            smstats.append({"url": sm, "error": repr(e)})
    return urls, smstats



def offer_summary(card):
    out = []
    seen = set()
    for o in card.get("offers", []):
        store = str(o.get("store") or "").strip()
        if not store:
            continue
        k = norm(store)
        if k in seen:
            continue
        seen.add(k)
        out.append({"store": store, "price": o.get("price")})
    return out

def physical_key(card):
    return (
        norm(card.get("set")),
        collector_parts(card.get("number")),
        norm(card.get("name")),
        str(card.get("variant") or ""),
    )

def main():
    started = time.monotonic()
    retail = json.loads(RETAIL.read_text(encoding="utf-8"))
    exact, loose, short_index, known_sets = build_indexes(retail)

    urls, smstats = discover()
    eligible = sorted(
        u for u in urls
        if "near-mint" in u.lower() and "italiano" in u.lower()
    )[:MAX_PRODUCTS]

    st = Counter(
        discoveredPokemonSingleUrls=len(urls),
        prefilteredNearMintItaliano=len(eligible),
    )
    exact_examples = []
    potential_examples = []
    rejected_examples = []
    unknown_sets = Counter()
    rarities = Counter()
    variant_signals = Counter()
    number_formats = Counter()
    rarity_variant_audit = Counter()
    structured_signal_audit = Counter()
    explicit_variant_examples = []
    unique_identity_examples = []
    centro_identity_candidates = []

    for i, u in enumerate(eligible, 1):
        if time.monotonic() - started >= MAX_RUNTIME_SECONDS:
            st["runtimeLimitReached"] += 1
            break

        st["attempted"] += 1
        print(f"[{i}/{len(eligible)}] {u}", flush=True)

        try:
            html, final, _ = get(u)
            st["fetched"] += 1
            p = parse_page(html, final)

            rarities[p["rarity"] or "(missing)"] += 1
            variant_signals[p["variantSignal"]] += 1
            structured_signal_audit[(
                p.get("rarity") or "(missing)",
                p.get("foiling") or "(missing)",
                p.get("reverseHolo") or "(missing)",
                p.get("firstEdition") or "(missing)",
                p.get("variantSignal") or "(missing)",
            )] += 1
            if p.get("variant") and len(explicit_variant_examples) < 50:
                explicit_variant_examples.append(p.copy())

            if norm(p["language"]) != "italiano":
                st["languageRejected"] += 1; continue
            if norm(p["condition"]) != "near mint":
                st["conditionRejected"] += 1; continue
            if p["available"] is False:
                st["unavailable"] += 1; continue
            if p["available"] is None:
                st["availabilityUnconfirmed"] += 1; continue
            if p["price"] is None:
                if len(p["priceCandidates"]) > 1:
                    st["priceAmbiguous"] += 1
                else:
                    st["priceUnavailable"] += 1
                continue

            cp = collector_parts(p["number"])
            if not cp:
                st["numberUnavailable"] += 1
                if len(rejected_examples) < 50:
                    rejected_examples.append({"reason": "numberUnavailable", "shop": p})
                continue

            prefix = cp[0] or "(numeric)"
            number_formats[prefix] += 1

            if not p["set"]:
                st["setUnavailable"] += 1; continue
            if not p["variant"]:
                st["variantUnconfirmed"] += 1
                sp = short_number_key(p["number"])
                if sp and p["set"]:
                    shop_set = norm(p["set"])
                    mapped_set = norm(SET_ALIASES.get(shop_set, p["set"]))
                    candidates = short_index.get((mapped_set, sp, norm(p["name"])), [])
                    physical = {
                        (norm(c.get("set")), collector_parts(c.get("number")), norm(c.get("name")))
                        for c in candidates
                    }
                    if len(physical) == 1 and candidates:
                        st["uniqueIdentityBySetNameNumber"] += 1
                        variants = sorted({str(c.get("variant")) for c in candidates})
                        cardoryx_numbers = sorted({str(c.get("number")) for c in candidates})

                        shop_exact = collector_parts(p["number"])
                        exact_same = any(collector_parts(c.get("number")) == shop_exact for c in candidates)

                        if exact_same:
                            st["uniqueIdentityFullNumberExact"] += 1
                            number_mode = "fullNumberExact"
                        else:
                            st["uniqueIdentityAbbreviatedNumber"] += 1
                            number_mode = "abbreviatedNumber"

                        if len(variants) == 1:
                            st["uniqueIdentitySingleCardoryxVariant"] += 1
                            unique_variant = variants[0]
                        else:
                            st["uniqueIdentityMultipleCardoryxVariants"] += 1
                            unique_variant = None

                        # Rarità rimane SOLO informativa: nessuna mappa rarity -> variant.
                        rarity_key = norm(p.get("rarity"))
                        if unique_variant:
                            st["singleVariantDiagnostic"] += 1
                            audit_key = f'{p.get("rarity") or "(missing)"} -> {unique_variant}'
                            rarity_variant_audit[audit_key] += 1

                        item = {
                            "reason": "diagnosticUniqueIdentity",
                            "numberMode": number_mode,
                            "shop": p,
                            "cardoryxNumbers": cardoryx_numbers,
                            "cardoryxVariants": variants,
                            "singleCardoryxVariant": unique_variant,
                            "rarityUsedForAcceptance": False,
                            "diagnosticOnly": True,
                        }
                        unique_identity_examples.append(item)
                        if unique_variant and len(candidates) == 1:
                            c0 = candidates[0]
                            centro_identity_candidates.append({
                                "identityKey": physical_key(c0),
                                "shop": p,
                                "cardoryx": c0,
                                "variantEstablishedByShopSignal": False,
                                "variantOnlyKnownFromUniqueCardoryxIdentity": True,
                            })
                        if len(rejected_examples) < 150:
                            rejected_examples.append(item)
                    elif len(physical) > 1:
                        st["abbreviatedNumberAmbiguousIdentity"] += 1
                    else:
                        st["abbreviatedNumberNoIdentity"] += 1
                continue

            st["usableBeforeIdentity"] += 1

            shop_set = norm(p["set"])
            mapped_set = norm(SET_ALIASES.get(shop_set, p["set"]))
            if mapped_set not in known_sets:
                st["setNotExactCardoryx"] += 1
                unknown_sets[p["set"]] += 1
                continue

            key = (mapped_set, cp, norm(p["name"]), p["variant"])
            matches = exact.get(key, [])

            if len(matches) == 1:
                st["exactMatches"] += 1
                c = matches[0]
                centro_identity_candidates.append({
                    "identityKey": physical_key(c),
                    "shop": p,
                    "cardoryx": c,
                    "variantEstablishedByShopSignal": True,
                    "variantOnlyKnownFromUniqueCardoryxIdentity": False,
                })
                n = store_count(c)
                if n >= 3:
                    st["matchedAlreadyReliable"] += 1
                elif n == 2:
                    st["newReliablePotential"] += 1
                else:
                    st["matchedCurrentlyNotReliable"] += 1

                item = {
                    "shop": p,
                    "cardoryx": {
                        "set": c.get("set"),
                        "number": c.get("number"),
                        "name": c.get("name"),
                        "variant": c.get("variant"),
                        "currentStores": n,
                        "currentlyReliable": n >= 3,
                    },
                }
                if len(exact_examples) < 100:
                    exact_examples.append(item)
                if n == 2 and len(potential_examples) < 100:
                    potential_examples.append(item)

            elif len(matches) > 1:
                st["identityAmbiguous"] += 1
            else:
                # Diagnostica sicura: stessa identita senza variante.
                lm = loose.get((mapped_set, cp, norm(p["name"])), [])
                if len(lm) == 1:
                    st["sameCardDifferentVariant"] += 1
                    if len(rejected_examples) < 50:
                        rejected_examples.append({
                            "reason": "sameCardDifferentVariant",
                            "shop": p,
                            "cardoryxVariant": lm[0].get("variant"),
                        })
                elif len(lm) > 1:
                    st["variantIdentityAmbiguous"] += 1
                else:
                    st["identityRejected"] += 1

        except Exception as e:
            st["errors"] += 1
            st["error_" + type(e).__name__] += 1
            if len(rejected_examples) < 50:
                rejected_examples.append({"reason": "error", "url": u, "error": repr(e)})

        time.sleep(SLEEP_SECONDS)


    groups = defaultdict(list)
    for x in centro_identity_candidates:
        groups[x["identityKey"]].append(x)

    physical_audit = []
    for _, group in groups.items():
        c = group[0]["cardoryx"]
        prices = sorted({round(float(x["shop"]["price"]), 2) for x in group if x["shop"].get("price") is not None})
        urls_group = sorted({x["shop"].get("url") for x in group if x["shop"].get("url")})
        structured_signatures = {
            (
                norm(x["shop"].get("set")), str(x["shop"].get("number") or ""),
                norm(x["shop"].get("rarity")), norm(x["shop"].get("foiling")),
                norm(x["shop"].get("reverseHolo")), norm(x["shop"].get("language")),
                norm(x["shop"].get("condition"))
            )
            for x in group
        }

        if len(group) == 1:
            duplicate_status = "single"
            safe = True
            st["safeSingleCentroOfferCandidates"] += 1
        elif len(prices) == 1 and len(structured_signatures) == 1:
            duplicate_status = "duplicateSamePriceCollapsedDiagnostic"
            safe = True
            st["duplicateSamePriceCollapsedDiagnostic"] += 1
        else:
            duplicate_status = "duplicateStoreOfferAmbiguous"
            safe = False
            st["duplicateDifferentPriceRejected"] += 1

        if len(group) > 1:
            st["duplicateIdentityGroups"] += 1

        existing = offer_summary(c)
        current = len(existing)
        if current == 0: st["currentStoreCount0"] += 1
        elif current == 1: st["currentStoreCount1"] += 1
        elif current == 2: st["currentStoreCount2"] += 1
        else: st["currentStoreCount3plus"] += 1

        if current >= 3:
            st["currentlyReliable"] += 1
            if safe:
                st["alreadyReliableWouldGainOffer"] += 1
        else:
            st["currentlyNotReliable"] += 1
            if safe and current == 2:
                st["potentialTwoToThreeStoreUpgrade"] += 1
            elif safe:
                st["noGainBecauseBelowThree"] += 1

        physical_audit.append({
            "cardoryx": {
                "set": c.get("set"), "number": c.get("number"),
                "name": c.get("name"), "variant": c.get("variant"),
            },
            "centroPages": len(group),
            "centroPrices": prices,
            "centroUrls": urls_group,
            "duplicateStatus": duplicate_status,
            "safeCentroOfferDiagnostic": safe,
            "variantEstablishedByShopSignal": any(x["variantEstablishedByShopSignal"] for x in group),
            "variantOnlyKnownFromUniqueCardoryxIdentity": all(x["variantOnlyKnownFromUniqueCardoryxIdentity"] for x in group),
            "currentIndependentStores": current,
            "existingOffers": existing,
            "wouldReachThreeStores": bool(safe and current == 2),
            "currentlyReliable": current >= 3,
        })

    st["uniquePhysicalIdentities"] = len(groups)
    st["crawlCompleted"] = int(st["attempted"] == len(eligible) and not st["runtimeLimitReached"])
    st["crawlRemaining"] = max(0, len(eligible) - st["attempted"])
    physical_audit.sort(key=lambda x: (
        not x["wouldReachThreeStores"],
        not x["safeCentroOfferDiagnostic"],
        norm(x["cardoryx"]["set"]),
        norm(x["cardoryx"]["name"]),
        str(x["cardoryx"]["number"]),
    ))


    report = {
        "schema": 15,
        "source": "Centro del Fumetto",
        "mode": "Centro-only complete crawl + structured-variant evidence + duplicate + retail-gain diagnostic",
        "rules": {
            "catalogPath": POKEMON_SINGLE_PATH,
            "urlPrefilter": "near-mint + italiano",
            "structuredFields": [
                "pa_ct_espansione", "pa_ct_condizione", "pa_ct_lingua",
                "pa_ct_numero_collezione", "pa_ct_rarita",
                "pa_ct_foiling", "pa_ct_reverse_holo", "pa_ct_first_edition"
            ],
            "language": "Italiano exact",
            "condition": "Near Mint exact",
            "availability": "JSON-LD/meta InStock required",
            "price": "single unambiguous product price only",
            "setRule": "exact Cardoryx set or existing trusted aliases only; no new aliases learned automatically",
            "variantRule": "only explicit structured Reverse/Holo signals may establish variant; Foiling=Normale and rarity never establish Normal/Full Art/special variants; unique Cardoryx variant remains diagnostic only",
            "identityRule": "Centro -> existing Cardoryx identity only; no external identity bridge; no new identities created",
            "createsNewIdentity": False,
            "duplicateStoreRule": "same physical identity counts Centro once; conflicting duplicate prices/structured fields are rejected, never auto-selected",
            "retailGainRule": "diagnostic only: measure current independent stores and safe 2-to-3 upgrades",
            "retailPricesModified": False,
        },
        "limits": {
            "maxProductsFetched": MAX_PRODUCTS,
            "maxRuntimeSeconds": MAX_RUNTIME_SECONDS,
        },
        "stats": dict(st),
        "topUnmappedSets": unknown_sets.most_common(50),
        "numberFormats": number_formats.most_common(30),
        "variantSignals": variant_signals.most_common(30),
        "structuredVariantSignalAudit": [
            {"rarity": k[0], "foiling": k[1], "reverseHolo": k[2], "firstEdition": k[3], "variantSignal": k[4], "count": v}
            for k, v in structured_signal_audit.most_common(100)
        ],
        "explicitStructuredVariantExamples": explicit_variant_examples,
        "raritiesSeen": rarities.most_common(60),
        "rarityToSingleCardoryxVariantAudit": rarity_variant_audit.most_common(100),
        "uniqueIdentityExamples": unique_identity_examples,
        "physicalIdentityAudit": physical_audit,
        "newReliablePotentialExamples": potential_examples,
        "exactExamples": exact_examples,
        "rejectedExamples": rejected_examples,
        "sitemaps": smstats,
    }

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["stats"], ensure_ascii=False, indent=2), flush=True)
    print("Report:", REPORT, flush=True)

if __name__ == "__main__":
    main()
