#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V9
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

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/9.0)"
TIMEOUT = 12
MAX_SITEMAPS = 120
MAX_PRODUCTS = 400
MAX_RUNTIME_SECONDS = 540
SLEEP_SECONDS = 0.05
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
                        st["abbreviatedNumberUniqueIdentity"] += 1
                        variants = sorted({str(c.get("variant")) for c in candidates})
                        if len(variants) == 1:
                            st["uniqueIdentitySingleCardoryxVariant"] += 1
                        else:
                            st["uniqueIdentityMultipleCardoryxVariants"] += 1
                        if len(rejected_examples) < 150:
                            rejected_examples.append({
                                "reason": "diagnosticUniqueShortNumber",
                                "shop": p,
                                "cardoryxNumbers": sorted({str(c.get("number")) for c in candidates}),
                                "cardoryxVariants": variants,
                                "diagnosticOnly": True,
                            })
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

    report = {
        "schema": 9,
        "source": "Centro del Fumetto",
        "mode": "read-only number-format + variant-safety diagnostic",
        "rules": {
            "catalogPath": POKEMON_SINGLE_PATH,
            "urlPrefilter": "near-mint + italiano",
            "structuredFields": [
                "pa_ct_espansione", "pa_ct_condizione", "pa_ct_lingua",
                "pa_ct_numero_collezione", "pa_ct_rarita",
                "pa_ct_foiling", "pa_ct_reverse_holo"
            ],
            "language": "Italiano exact",
            "condition": "Near Mint exact",
            "availability": "JSON-LD/meta InStock required",
            "price": "single unambiguous product price only",
            "setRule": "exact normalized set only; no new aliases in V7",
            "variantRule": "rarity never maps to variant; Foiling=Normale is diagnostic only and is NOT accepted as Cardoryx Normal",
            "identityRule": "accepted match remains exact set + full collector number + exact normalized name + explicit safe variant; short-number matches are diagnostic only",
            "createsNewIdentity": False,
            "cardmarketTouched": False,
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
        "raritiesSeen": rarities.most_common(60),
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
