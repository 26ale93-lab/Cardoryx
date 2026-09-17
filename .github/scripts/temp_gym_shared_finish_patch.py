from pathlib import Path


def replace_once(s, old, new, label):
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: expected 1 anchor, found {n}')
    return s.replace(old,new,1)

# ---------- index.html ----------
p=Path('index.html')
s=p.read_text()

anchor="""const VERIFIED_VARIANT_PRICES = {
"""
registry="""const VERIFIED_GYM_SHARED_FINISH_PRODUCTS={
  'gym1-15':{setId:'gym1',localId:'15',name:'Brock',finish:'Holo',productId:274151,expansionId:1529,pairId:'gym1-98'},
  'gym1-98':{setId:'gym1',localId:'98',name:'Brock',finish:'Normal',productId:274151,expansionId:1529,pairId:'gym1-15'},
  'gym1-16':{setId:'gym1',localId:'16',name:'Erika',finish:'Holo',productId:274152,expansionId:1529,pairId:'gym1-100'},
  'gym1-100':{setId:'gym1',localId:'100',name:'Erika',finish:'Normal',productId:274152,expansionId:1529,pairId:'gym1-16'},
  'gym1-17':{setId:'gym1',localId:'17',name:'Lt. Surge',finish:'Holo',productId:274153,expansionId:1529,pairId:'gym1-101'},
  'gym1-101':{setId:'gym1',localId:'101',name:'Lt. Surge',finish:'Normal',productId:274153,expansionId:1529,pairId:'gym1-17'},
  'gym1-18':{setId:'gym1',localId:'18',name:'Misty',finish:'Holo',productId:274154,expansionId:1529,pairId:'gym1-102'},
  'gym1-102':{setId:'gym1',localId:'102',name:'Misty',finish:'Normal',productId:274154,expansionId:1529,pairId:'gym1-18'},
  'gym2-17':{setId:'gym2',localId:'17',name:'Blaine',finish:'Holo',productId:274285,expansionId:1530,pairId:'gym2-100'},
  'gym2-100':{setId:'gym2',localId:'100',name:'Blaine',finish:'Normal',productId:274285,expansionId:1530,pairId:'gym2-17'},
  'gym2-18':{setId:'gym2',localId:'18',name:'Giovanni',finish:'Holo',productId:274286,expansionId:1530,pairId:'gym2-104'},
  'gym2-104':{setId:'gym2',localId:'104',name:'Giovanni',finish:'Normal',productId:274286,expansionId:1530,pairId:'gym2-18'},
  'gym2-19':{setId:'gym2',localId:'19',name:'Koga',finish:'Holo',productId:274287,expansionId:1530,pairId:'gym2-106'},
  'gym2-106':{setId:'gym2',localId:'106',name:'Koga',finish:'Normal',productId:274287,expansionId:1530,pairId:'gym2-19'},
  'gym2-20':{setId:'gym2',localId:'20',name:'Sabrina',finish:'Holo',productId:274288,expansionId:1530,pairId:'gym2-110'},
  'gym2-110':{setId:'gym2',localId:'110',name:'Sabrina',finish:'Normal',productId:274288,expansionId:1530,pairId:'gym2-20'}
};
const VERIFIED_GYM_SHARED_PRICE_GUIDES={
  274151:{idProduct:274151,trend:31.30,avg7:30.86,avg30:35.88,avg:35.39,low:10,'trend-holo':23.27,'avg7-holo':25.93,'avg30-holo':15.31},
  274152:{idProduct:274152,trend:44.25,avg7:48.35,avg30:41.07,avg:44.56,low:18,'trend-holo':37.42,'avg7-holo':44.56,'avg30-holo':25.65},
  274153:{idProduct:274153,trend:30.95,avg7:34.08,avg30:30.15,avg:31.46,low:6,'trend-holo':22.68,'avg7-holo':24.79,'avg30-holo':22.13},
  274154:{idProduct:274154,trend:39.46,avg7:36.66,avg30:56.73,avg:35.62,low:22.89,'trend-holo':19.12,'avg7-holo':18.65,'avg30-holo':16.42},
  274285:{idProduct:274285,trend:52.47,avg7:101.08,avg30:59.92,avg:76.97,low:12.9,'trend-holo':24.93,'avg7-holo':29.60,'avg30-holo':22.43},
  274286:{idProduct:274286,trend:61.45,avg7:59.99,avg30:61.13,avg:58.74,low:24,'trend-holo':27.31,'avg7-holo':36.00,'avg30-holo':24.58},
  274287:{idProduct:274287,trend:45.76,avg7:48.36,avg30:43.43,avg:47.92,low:10,'trend-holo':26.88,'avg7-holo':28.79,'avg30-holo':23.25},
  274288:{idProduct:274288,trend:79.05,avg7:59.25,avg30:55.96,avg:53.79,low:22,'trend-holo':22.98,'avg7-holo':26.07,'avg30-holo':23.32}
};
function verifiedGymLeaderSharedFinishPrice(card,variant){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const rule=VERIFIED_GYM_SHARED_FINISH_PRODUCTS[id];
  if(!rule||cardSetId(card)!==rule.setId||exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId)||normText(card?.name||'')!==normText(rule.name))return null;
  const target=canonicalVariant(variant||'Normal');
  if(target!==rule.finish)return null;
  const expectedType=target==='Holo'?'holo':'normal';
  const rows=tcgdexVariantDetails(card).filter(row=>{
    const stamps=Array.isArray(row?.stamp)?row.stamp:[];
    const cm=row?.pricing?.cardmarket||{};
    return stamps.length===1&&normText(stamps[0])===normText('1st-edition')&&
      canonicalFinishTypeLabel(row?.type)===expectedType&&!canonicalFinishFoilLabel(row?.foil)&&
      String(row?.size||'standard').trim().toLowerCase()==='standard'&&
      Number(row?.thirdParty?.cardmarket||0)===rule.productId&&Number(cm?.idProduct||cm?.id_product||0)===rule.productId;
  });
  const live=rows.length===1?(rows[0]?.pricing?.cardmarket||null):null;
  const cm=live||VERIFIED_GYM_SHARED_PRICE_GUIDES[rule.productId]||null;
  if(!cm||Number(cm?.idProduct||cm?.id_product||0)!==rule.productId)return null;
  const pick=(base)=>{
    const key=target==='Holo'?`${base}-holo`:base;
    const v=Number(cm?.[key]||0);return Number.isFinite(v)&&v>0?v:null;
  };
  const out={idProduct:rule.productId,trend:pick('trend'),avg7:pick('avg7'),avg30:pick('avg30'),avg:pick('avg'),low:pick('low'),
    source:`Cardmarket · ${rule.setId==='gym1'?'Gym Heroes':'Gym Challenge'} · ${rule.name} ${rule.localId} · ${target} · product ${rule.productId}`,
    verified:String(cm?.updated||'2026-09-17T20:17:05Z')};
  if(![out.trend,out.avg7,out.avg30,out.avg,out.low].some(v=>Number(v)>0))return null;
  return out;
}

"""
s=replace_once(s,anchor,registry+anchor,'Gym runtime registry')

old="""function verifiedVariantPrice(card,variant){
  const exact=verifiedExactVariantPrice(card,variant);
"""
new="""function verifiedVariantPrice(card,variant){
  const gymShared=verifiedGymLeaderSharedFinishPrice(card,variant);
  if(gymShared)return gymShared;
  const exact=verifiedExactVariantPrice(card,variant);
"""
s=replace_once(s,old,new,'Gym verifiedVariantPrice chain')
p.write_text(s)

# ---------- audit script ----------
p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text()
anchor="""BATCH2_SHARED_PRODUCT_OWNERS = {
"""
const="""GYM_SHARED_FINISH_PRODUCTS = {
    "gym1-15": ("gym1","15","Brock","Holo",274151,1529,"gym1-98"),
    "gym1-98": ("gym1","98","Brock","Normal",274151,1529,"gym1-15"),
    "gym1-16": ("gym1","16","Erika","Holo",274152,1529,"gym1-100"),
    "gym1-100": ("gym1","100","Erika","Normal",274152,1529,"gym1-16"),
    "gym1-17": ("gym1","17","Lt. Surge","Holo",274153,1529,"gym1-101"),
    "gym1-101": ("gym1","101","Lt. Surge","Normal",274153,1529,"gym1-17"),
    "gym1-18": ("gym1","18","Misty","Holo",274154,1529,"gym1-102"),
    "gym1-102": ("gym1","102","Misty","Normal",274154,1529,"gym1-18"),
    "gym2-17": ("gym2","17","Blaine","Holo",274285,1530,"gym2-100"),
    "gym2-100": ("gym2","100","Blaine","Normal",274285,1530,"gym2-17"),
    "gym2-18": ("gym2","18","Giovanni","Holo",274286,1530,"gym2-104"),
    "gym2-104": ("gym2","104","Giovanni","Normal",274286,1530,"gym2-18"),
    "gym2-19": ("gym2","19","Koga","Holo",274287,1530,"gym2-106"),
    "gym2-106": ("gym2","106","Koga","Normal",274287,1530,"gym2-19"),
    "gym2-20": ("gym2","20","Sabrina","Holo",274288,1530,"gym2-110"),
    "gym2-110": ("gym2","110","Sabrina","Normal",274288,1530,"gym2-20"),
}

"""
s=replace_once(s,anchor,const+anchor,'Gym audit registry')

anchor="""        elif card_id in BATCH2_SHARED_PRODUCT_OWNERS:
"""
branch="""        elif card_id in GYM_SHARED_FINISH_PRODUCTS:
            owner_set, owner_local, owner_name, owner_finish, owner_product, expansion_id, pair_id = GYM_SHARED_FINISH_PRODUCTS[card_id]
            catalogue = products.get(owner_product) or {}
            guide = prices.get(owner_product) or {}
            identity_ok = bool((card.get("set") or {}).get("id") == owner_set and norm_local(card.get("localId")) == norm_local(owner_local) and card_identity(card).get("name") == owner_name)
            expected_type = "holo" if owner_finish == "Holo" else "normal"
            live_rows=[]
            for row in live_card_detail.get("variants_detailed") or []:
                stamps=row.get("stamp") or []
                if isinstance(stamps,str): stamps=[stamps]
                cm=((row.get("pricing") or {}).get("cardmarket") or {})
                try: ppid=int(cm.get("idProduct") or cm.get("id_product"))
                except (TypeError,ValueError): ppid=None
                if (sorted(map(str,stamps)) == ["1st-edition"] and str(row.get("type") or "").lower() == expected_type and not row.get("foil") and str(row.get("size") or "standard").lower() == "standard" and cm_id(row) == owner_product and ppid == owner_product):
                    live_rows.append(row)
            pair=GYM_SHARED_FINISH_PRODUCTS.get(pair_id)
            pair_ok=bool(pair and pair[0] == owner_set and pair[2] == owner_name and pair[4] == owner_product and pair[3] != owner_finish and pair[1] != owner_local and pair[6] == card_id)
            catalogue_ok=bool(catalogue and int(catalogue.get("idExpansion") or 0)==expansion_id and catalogue.get("name")==owner_name)
            relevant_keys=("trend-holo","avg7-holo","avg30-holo","avg-holo","low-holo") if owner_finish=="Holo" else ("trend","avg7","avg30","avg","low")
            guide_ok=bool(guide and int(guide.get("idProduct") or 0)==owner_product and any(isinstance(guide.get(k),(int,float)) and guide.get(k)>0 for k in relevant_keys))
            source_guard=("VERIFIED_GYM_SHARED_FINISH_PRODUCTS" in source and "verifiedGymLeaderSharedFinishPrice" in source)
            if identity_ok and len(live_rows)==1 and pair_ok and catalogue_ok and guide_ok and source_guard:
                classification, priority, confidence = "SAFE", None, "HIGH"
                resolved_pid=owner_product
                resolved_value=next((guide.get(k) for k in relevant_keys if isinstance(guide.get(k),(int,float)) and guide.get(k)>0), None)
                reason=("Gym Heroes/Gym Challenge hanno due checklist fisiche distinte per lo stesso Leader: numero Holo e numero Non Holo. Cardmarket le accorpa nello stesso productId ma separa i valori standard e *-holo; Cardoryx usa set, numero, nome e finitura esatti prima di leggere il relativo campo prezzo.")
                action="Mantenere il resolver sulle sole 16 identità verificate; nessuna regola generica per 1st Edition o altri prodotti condivisi."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason="La coppia Gym Leader condivisa non supera più tutti i gate esatti di checklist, prodotto, finitura o Price Guide."
                action="Fail-closed; nessun riuso generico del productId condiviso."
"""
s=replace_once(s,anchor,branch+anchor,'Gym audit classification')

# Permanent runtime regression before main().
anchor='\ndef main():\n'
runtime="""
def runtime_gym_shared_finish_regression():
    source=INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker=re.search(rf"\\bfunction\\s+{re.escape(name)}\\s*\\(",source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{",marker.end());depth=0;quote=None;esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'",'"',"`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    fixtures={};errors={};cache=Path(tempfile.gettempdir())/"cardoryx_gym_shared_finish_v1"
    for card_id in GYM_SHARED_FINISH_PRODUCTS:
        value,error=live_card(card_id,cache)
        if value: fixtures[card_id]=value
        if error: errors[card_id]=error
    if errors or len(fixtures)!=len(GYM_SHARED_FINISH_PRODUCTS): raise AssertionError(f"Gym live regression unavailable: {errors}")
    start=source.index("const VERIFIED_GYM_SHARED_FINISH_PRODUCTS=")
    end=source.index("const VERIFIED_VARIANT_PRICES =",start)
    registry=source[start:end]
    names=("normText","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel","cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails")
    js="\\n".join(extract_fn(n) for n in names)+"\\n"+registry
    harness=r'''\nconst fixtures=JSON.parse(process.argv[1]);\nconst rules=JSON.parse(process.argv[2]);\nfunction fail(m){throw new Error(m)}\nconst out={};\nfor(const [id,r] of Object.entries(rules)){\n  const [setId,localId,name,finish,pid,exp,pairId]=r,c=fixtures[id];\n  const ok=verifiedGymLeaderSharedFinishPrice(c,finish);\n  if(!ok||Number(ok.idProduct)!==Number(pid))fail(id+' exact product mismatch');\n  const row=(c.variants_detailed||[]).find(x=>Number(x?.thirdParty?.cardmarket||0)===Number(pid)&&(x.stamp||[]).includes('1st-edition')&&String(x.type||'').toLowerCase()===(finish==='Holo'?'holo':'normal'));\n  const cm=row?.pricing?.cardmarket||{};\n  const expected=Number(finish==='Holo'?cm['trend-holo']:cm.trend);\n  if(!(expected>0)||Math.abs(Number(ok.trend)-expected)>1e-9)fail(id+' wrong price field');\n  if(verifiedGymLeaderSharedFinishPrice(c,finish==='Holo'?'Normal':'Holo')!==null)fail(id+' wrong finish accepted');\n  for(const mutated of [{...c,localId:'999'},{...c,name:name+' wrong'},{...c,set:{...(c.set||{}),id:setId+'x'}}]) if(verifiedGymLeaderSharedFinishPrice(mutated,finish)!==null)fail(id+' wrong identity accepted');\n  const pair=rules[pairId];if(!pair||pair[4]!==pid||pair[3]===finish||pair[2]!==name)fail(id+' pair registry invalid');\n  out[id]={productId:ok.idProduct,finish,trend:ok.trend};\n}\nprocess.stdout.write(JSON.stringify(out));\n'''
    return json.loads(subprocess.check_output(["node","-e",js+"\\n"+harness,json.dumps(fixtures,ensure_ascii=False),json.dumps(GYM_SHARED_FINISH_PRODUCTS)],text=True))

"""
s=replace_once(s,anchor,runtime+anchor,'Gym runtime regression')

old='    runtime_regression["mfbPokeball"] = runtime_mfb_pokeball_regression()\n'
new=old+'    runtime_regression["gymSharedFinish"] = runtime_gym_shared_finish_regression()\n'
s=replace_once(s,old,new,'Gym runtime regression call')
p.write_text(s)
print('Gym shared-finish patch applied')
