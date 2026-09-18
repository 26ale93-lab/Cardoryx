import json
import pathlib
import re
import tempfile
import urllib.request

INDEX = pathlib.Path("index.html")
AUDIT = pathlib.Path("scripts/test_card_identity_cardmarket_audit.py")

ROWS = [
    ("gym1-15","gym1","15","Brock","Holo",274151,274151,1529,"gym1-98"),
    ("gym1-98","gym1","98","Brock","Normal",274234,274151,1529,"gym1-15"),
    ("gym1-16","gym1","16","Erika","Holo",274152,274152,1529,"gym1-100"),
    ("gym1-100","gym1","100","Erika","Normal",274236,274152,1529,"gym1-16"),
    ("gym1-17","gym1","17","Lt. Surge","Holo",274153,274153,1529,"gym1-101"),
    ("gym1-101","gym1","101","Lt. Surge","Normal",274237,274153,1529,"gym1-17"),
    ("gym1-18","gym1","18","Misty","Holo",274154,274154,1529,"gym1-102"),
    ("gym1-102","gym1","102","Misty","Normal",274238,274154,1529,"gym1-18"),
    ("gym2-17","gym2","17","Blaine","Holo",274285,274285,1530,"gym2-100"),
    ("gym2-100","gym2","100","Blaine","Normal",274368,274285,1530,"gym2-17"),
    ("gym2-18","gym2","18","Giovanni","Holo",274286,274286,1530,"gym2-104"),
    ("gym2-104","gym2","104","Giovanni","Normal",274372,274286,1530,"gym2-18"),
    ("gym2-19","gym2","19","Koga","Holo",274287,274287,1530,"gym2-106"),
    ("gym2-106","gym2","106","Koga","Normal",274374,274287,1530,"gym2-19"),
    ("gym2-20","gym2","20","Sabrina","Holo",274288,274288,1530,"gym2-110"),
    ("gym2-110","gym2","110","Sabrina","Normal",274378,274288,1530,"gym2-20"),
    ("neo2-2","neo2","2","Forretress","Holo",274513,274513,1532,"neo2-21"),
    ("neo2-21","neo2","21","Forretress","Normal",274532,274513,1532,"neo2-2"),
    ("neo2-3","neo2","3","Hitmontop","Holo",274514,274514,1532,"neo2-22"),
    ("neo2-22","neo2","22","Hitmontop","Normal",274533,274514,1532,"neo2-3"),
    ("neo2-4","neo2","4","Houndoom","Holo",274515,274515,1532,"neo2-23"),
    ("neo2-23","neo2","23","Houndoom","Normal",274534,274515,1532,"neo2-4"),
    ("neo2-5","neo2","5","Houndour","Holo",274516,274516,1532,"neo2-24"),
    ("neo2-24","neo2","24","Houndour","Normal",274535,274516,1532,"neo2-5"),
    ("neo2-6","neo2","6","Kabutops","Holo",274517,274517,1532,"neo2-25"),
    ("neo2-25","neo2","25","Kabutops","Normal",274536,274517,1532,"neo2-6"),
    ("neo2-7","neo2","7","Magnemite","Holo",274518,274518,1532,"neo2-26"),
    ("neo2-26","neo2","26","Magnemite","Normal",274537,274518,1532,"neo2-7"),
    ("neo2-8","neo2","8","Politoed","Holo",274519,274519,1532,"neo2-27"),
    ("neo2-27","neo2","27","Politoed","Normal",274538,274519,1532,"neo2-8"),
    ("neo2-9","neo2","9","Poliwrath","Holo",274520,274520,1532,"neo2-28"),
    ("neo2-28","neo2","28","Poliwrath","Normal",274539,274520,1532,"neo2-9"),
    ("neo2-10","neo2","10","Scizor","Holo",274521,274521,1532,"neo2-29"),
    ("neo2-29","neo2","29","Scizor","Normal",274540,274521,1532,"neo2-10"),
    ("neo2-11","neo2","11","Smeargle","Holo",274522,274522,1532,"neo2-30"),
    ("neo2-30","neo2","30","Smeargle","Normal",274541,274522,1532,"neo2-11"),
    ("neo2-12","neo2","12","Tyranitar","Holo",274523,274523,1532,"neo2-31"),
    ("neo2-31","neo2","31","Tyranitar","Normal",274542,274523,1532,"neo2-12"),
    ("neo2-14","neo2","14","Unown [A]","Holo",274525,274525,1532,"neo2-33"),
    ("neo2-33","neo2","33","Unown [A]","Normal",274544,274525,1532,"neo2-14"),
    ("neo2-15","neo2","15","Ursaring","Holo",274526,274526,1532,"neo2-34"),
    ("neo2-34","neo2","34","Ursaring","Normal",274545,274526,1532,"neo2-15"),
    ("neo2-16","neo2","16","Wobbuffet","Holo",274527,274527,1532,"neo2-35"),
    ("neo2-35","neo2","35","Wobbuffet","Normal",274546,274527,1532,"neo2-16"),
    ("neo2-17","neo2","17","Yanma","Holo",274528,274528,1532,"neo2-36"),
    ("neo2-36","neo2","36","Yanma","Normal",274547,274528,1532,"neo2-17"),
]

def download_json(section, name):
    path = pathlib.Path(tempfile.gettempdir()) / name
    req = urllib.request.Request(
        "https://downloads.s3.cardmarket.com/productCatalog/" + section + "/" + name,
        headers={"User-Agent":"Cardoryx-Cardmarket-Identity-Audit/2.0"},
    )
    with urllib.request.urlopen(req, timeout=300) as response, path.open("wb") as fh:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    return json.load(path.open())

def rows_from(obj, keys):
    if isinstance(obj, list):
        return obj
    for key in keys:
        value = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(value, list):
            return value
    return []

def js_string(v):
    return json.dumps(v, ensure_ascii=False)

def build_js_registry(guides):
    entries = []
    for cid,set_id,local_id,name,finish,pid,source_pid,expansion_id,pair_id in ROWS:
        entries.append(
            "  " + js_string(cid) + ":{setId:" + js_string(set_id) +
            ",localId:" + js_string(local_id) + ",name:" + js_string(name) +
            ",finish:" + js_string(finish) + ",productId:" + str(pid) +
            ",sourceProduct:" + str(source_pid) + ",expansionId:" + str(expansion_id) +
            ",pairId:" + js_string(pair_id) + "}"
        )
    registry = "const VERIFIED_LEGACY_CHECKLIST_PRODUCTS={\n" + ",\n".join(entries) + "\n};\n"
    registry += "const VERIFIED_LEGACY_CHECKLIST_PRICE_GUIDES=" + json.dumps(guides, ensure_ascii=False, separators=(",",":")) + ";\n"
    registry += r'''
function verifiedLegacyChecklistCardmarketPrice(card,variant){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const rule=VERIFIED_LEGACY_CHECKLIST_PRODUCTS[id];
  if(!rule||cardSetId(card)!==rule.setId||exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId)||normText(card?.name||'')!==normText(rule.name))return null;
  const target=canonicalVariant(variant||'Normal');
  if(target!==rule.finish)return null;
  const expectedType=target==='Holo'?'holo':'normal';
  const liveRow=tcgdexVariantDetails(card).find(row=>{
    const stamps=Array.isArray(row?.stamp)?row.stamp:[];
    const cm=row?.pricing?.cardmarket||{};
    return stamps.length===0&&canonicalFinishTypeLabel(row?.type)===expectedType&&!canonicalFinishFoilLabel(row?.foil)&&
      String(row?.size||'standard').trim().toLowerCase()==='standard'&&
      Number(row?.thirdParty?.cardmarket||0)===rule.productId&&Number(cm?.idProduct||cm?.id_product||0)===rule.productId;
  });
  const live=liveRow?.pricing?.cardmarket||null;
  const snapshot=VERIFIED_LEGACY_CHECKLIST_PRICE_GUIDES[String(rule.productId)]||null;
  const cm=snapshot||live;
  if(!cm||Number(cm?.idProduct||cm?.id_product||0)!==rule.productId)return null;
  const pick=(base)=>{const v=Number(cm?.[base]||0);return Number.isFinite(v)&&v>0?v:null;};
  const out={idProduct:rule.productId,trend:pick('trend'),avg7:pick('avg7'),avg30:pick('avg30'),avg:pick('avg'),low:pick('low'),
    source:'Cardmarket · checklist fisica esatta · '+rule.setId+' '+rule.localId+' · '+target+' · product '+rule.productId,
    verified:String(cm?.updated||'2026-09-18')};
  if(![out.trend,out.avg7,out.avg30,out.avg,out.low].some(v=>Number(v)>0))return null;
  return out;
}
'''
    return registry

def build_py_registry():
    lines = ["LEGACY_CHECKLIST_PRODUCTS = {"]
    for cid,set_id,local_id,name,finish,pid,source_pid,expansion_id,pair_id in ROWS:
        lines.append("    " + repr(cid) + ": " + repr((set_id,local_id,name,finish,pid,source_pid,expansion_id,pair_id)) + ",")
    lines.append("}")
    return "\n".join(lines) + "\n"

product_catalogue = download_json("productList", "products_singles_6.json")
price_guide = download_json("priceGuide", "price_guide_6.json")
products = {int(r.get("idProduct") or 0): r for r in rows_from(product_catalogue, ("products",)) if r.get("idProduct")}
prices = {int(r.get("idProduct") or 0): r for r in rows_from(price_guide, ("priceGuides","priceGuide")) if r.get("idProduct")}

# Fail closed unless every proposed pair is independently supported by the official catalogue:
# exact product and current TCGdex source product must be same expansion, same name and same metacard.
for cid,set_id,local_id,name,finish,pid,source_pid,expansion_id,pair_id in ROWS:
    p = products.get(pid)
    s = products.get(source_pid)
    if not p or not s:
        raise SystemExit("Missing catalogue row for " + cid)
    if int(p.get("idExpansion") or 0) != expansion_id or int(s.get("idExpansion") or 0) != expansion_id:
        raise SystemExit("Wrong expansion for " + cid)
    if p.get("name") != s.get("name"):
        raise SystemExit("Catalogue name mismatch for " + cid)
    if int(p.get("idMetacard") or 0) <= 0 or int(p.get("idMetacard") or 0) != int(s.get("idMetacard") or -1):
        raise SystemExit("Metacard mismatch for " + cid)
    guide = prices.get(pid)
    if not guide or not any(isinstance(guide.get(k),(int,float)) and guide.get(k) > 0 for k in ("trend","avg7","avg30","avg","low")):
        raise SystemExit("Missing standard Price Guide fields for " + cid)

# Snapshot every exact Cardmarket product. Runtime valuation is anchored to the
# official product ID, never to the counterpart product or to *-holo fields.
exact_product_ids = sorted({pid for _,_,_,_,_,pid,_,_,_ in ROWS})
guides = {}
for pid in exact_product_ids:
    g = prices[pid]
    guides[str(pid)] = {k:g.get(k) for k in ("idProduct","avg","low","trend","avg1","avg7","avg30")}

idx = INDEX.read_text(encoding="utf-8")
start = idx.index("const VERIFIED_GYM_SHARED_FINISH_PRODUCTS={")
end = idx.index("const VERIFIED_VARIANT_PRICES =", start)
idx = idx[:start] + build_js_registry(guides) + "\n" + idx[end:]
old = """function verifiedVariantPrice(card,variant){
  const gymShared=verifiedGymLeaderSharedFinishPrice(card,variant);
  if(gymShared)return gymShared;
"""
new = """function verifiedVariantPrice(card,variant){
  const legacyChecklist=verifiedLegacyChecklistCardmarketPrice(card,variant);
  if(legacyChecklist)return legacyChecklist;
"""
if old not in idx:
    raise SystemExit("verifiedVariantPrice Gym anchor missing")
idx = idx.replace(old, new, 1)
INDEX.write_text(idx, encoding="utf-8")

aud = AUDIT.read_text(encoding="utf-8")
start = aud.index("GYM_SHARED_FINISH_PRODUCTS = {")
end = aud.index("BATCH2_SHARED_PRODUCT_OWNERS = {", start)
aud = aud[:start] + build_py_registry() + "\n" + aud[end:]

runtime = r'''def runtime_legacy_checklist_regression():
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


'''
start = aud.index("def runtime_gym_shared_finish_regression():")
end = aud.index("\ndef main():", start)
aud = aud[:start] + runtime + aud[end:]
old = '    runtime_regression["gymSharedFinish"] = runtime_gym_shared_finish_regression()'
new = '    runtime_regression["legacyChecklistProducts"] = runtime_legacy_checklist_regression()'
if old not in aud:
    raise SystemExit("runtime main anchor missing")
aud = aud.replace(old, new, 1)

classification = r'''        elif card_id in LEGACY_CHECKLIST_PRODUCTS:
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
                base_ok=(str(row.get("type") or "").lower()==expected_type and not row.get("foil") and str(row.get("size") or "standard").lower()=="standard")
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
'''
start = aud.index("        elif card_id in GYM_SHARED_FINISH_PRODUCTS:")
end = aud.index("        elif card_id in BATCH2_SHARED_PRODUCT_OWNERS:", start)
aud = aud[:start] + classification + aud[end:]
AUDIT.write_text(aud, encoding="utf-8")

print("PATCHED", len(ROWS), "identities", len(exact_product_ids), "exact Cardmarket products")
