from pathlib import Path


def replace_once(s, old, new, label):
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: expected 1 anchor, found {n}')
    return s.replace(old,new,1)

# ---------------- index.html ----------------
p=Path('index.html')
s=p.read_text()

ui='<option value="Worlds 2024">Worlds 2024</option>'
if s.count(ui)!=2:
    raise SystemExit(f'UI Worlds anchor expected 2, found {s.count(ui)}')
s=s.replace(ui, ui+'\n          <option value="MFB Poké Ball">MFB Poké Ball</option>')

old="  if(n.includes('worlds2024'))return 'Worlds 2024';\n"
new=old+"  if(n.includes('mfb poke ball')||n.includes('my first battle poke ball'))return 'MFB Poké Ball';\n"
s=replace_once(s,old,new,'canonical MFB stamp')

anchor='const VERIFIED_PRIMARY_WORLDS_STAMPS={\n'
registry="""const VERIFIED_MFB_POKEBALL_ROWS={
  'mfb-1':{setId:'mfb',localId:'1',name:'Bulbasaur',deckToken:'bulbasaur',baseProductId:741976,pokeballProductId:741975},
  'mfb-8':{setId:'mfb',localId:'8',name:'Grass Energy',deckToken:'bulbasaur',baseProductId:741986,pokeballProductId:741985},
  'mfb-16':{setId:'mfb',localId:'16',name:'Fire Energy',deckToken:'charmander',baseProductId:741998,pokeballProductId:741997},
  'mfb-17':{setId:'mfb',localId:'17',name:'Pikachu',deckToken:'pikachu',baseProductId:742000,pokeballProductId:741999},
  'mfb-24':{setId:'mfb',localId:'24',name:'Lightning Energy',deckToken:'pikachu',baseProductId:742010,pokeballProductId:742009},
  'mfb-25':{setId:'mfb',localId:'25',name:'Squirtle',deckToken:'squirtle',baseProductId:742012,pokeballProductId:742011}
};
function verifiedMfbPokeballRule(card){
  const id=String(card?.tcgdexId||card?.id||'').trim();
  const rule=VERIFIED_MFB_POKEBALL_ROWS[id];
  if(!rule||cardSetId(card)!==rule.setId||exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId)||normText(card?.name||'')!==normText(rule.name))return null;
  return rule;
}
function tcgdexExactMfbPokeballRow(card){
  const rule=verifiedMfbPokeballRule(card);if(!rule)return null;
  const expected=[rule.deckToken,'pokeball'].map(normText).sort();
  const rows=tcgdexVariantDetails(card).filter(row=>{
    const stamps=(Array.isArray(row?.stamp)?row.stamp:[]).map(normText).sort();
    const pid=Number(row?.thirdParty?.cardmarket||0),cm=row?.pricing?.cardmarket||{},ppid=Number(cm?.idProduct||cm?.id_product||0);
    return stamps.length===expected.length&&stamps.every((v,i)=>v===expected[i])&&canonicalFinishTypeLabel(row?.type)==='normal'&&!canonicalFinishFoilLabel(row?.foil)&&String(row?.size||'standard').trim().toLowerCase()==='standard'&&pid===rule.pokeballProductId&&ppid===rule.pokeballProductId;
  });
  return rows.length===1?rows[0]:null;
}

"""
s=replace_once(s,anchor,registry+anchor,'MFB registry')

old="""  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){
    return st==='30° Anniversario'||st==='Altro';
  }
  if(st==='None'||st==='Altro')return true;
"""
new="""  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){
    return st==='30° Anniversario'||st==='Altro';
  }
  if(st==='MFB Poké Ball')return !!tcgdexExactMfbPokeballRow(card);
  if(st==='None'||st==='Altro')return true;
"""
s=replace_once(s,old,new,'stampExists MFB')

anchor='function tcgdexExactWorldsStampPrice(card,variant,stamp){\n'
resolver="""function tcgdexExactMfbPokeballPrice(card,variant,stamp){
  if(canonicalVariant(variant||'Normal')!=='Normal'||canonicalStamp(stamp)!=='MFB Poké Ball')return null;
  const rule=verifiedMfbPokeballRule(card);if(!rule)return null;
  const row=tcgdexExactMfbPokeballRow(card);if(!row)return null;
  const cm=row?.pricing?.cardmarket||{};
  const usable=['trend','avg7','avg30','avg','low'].some(k=>Number(cm?.[k]||0)>0);
  if(!usable)return null;
  return {...cm,idProduct:rule.pokeballProductId,source:`TCGdex · Cardmarket · My First Battle Poké Ball · product ${rule.pokeballProductId}`,verified:String(cm?.updated||'')};
}

"""
s=replace_once(s,anchor,resolver+anchor,'MFB resolver')

old="""  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
  if(swsh028GameStop)return swsh028GameStop;
  const worldsExact=tcgdexExactWorldsStampPrice(card,variant,stamp);
"""
new="""  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
  if(swsh028GameStop)return swsh028GameStop;
  const mfbPokeball=tcgdexExactMfbPokeballPrice(card,variant,stamp);
  if(mfbPokeball)return mfbPokeball;
  const worldsExact=tcgdexExactWorldsStampPrice(card,variant,stamp);
"""
s=replace_once(s,old,new,'verifiedStampPrice MFB chain')
p.write_text(s)

# ---------------- audit script ----------------
p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text()

anchor='VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS = {\n'
const="""MFB_POKEBALL_EXACT_ROWS = {
    "mfb-1": {"setId":"mfb","localId":"1","name":"Bulbasaur","deckToken":"bulbasaur","base":741976,"pokeball":741975},
    "mfb-8": {"setId":"mfb","localId":"8","name":"Grass Energy","deckToken":"bulbasaur","base":741986,"pokeball":741985},
    "mfb-16": {"setId":"mfb","localId":"16","name":"Fire Energy","deckToken":"charmander","base":741998,"pokeball":741997},
    "mfb-17": {"setId":"mfb","localId":"17","name":"Pikachu","deckToken":"pikachu","base":742000,"pokeball":741999},
    "mfb-24": {"setId":"mfb","localId":"24","name":"Lightning Energy","deckToken":"pikachu","base":742010,"pokeball":742009},
    "mfb-25": {"setId":"mfb","localId":"25","name":"Squirtle","deckToken":"squirtle","base":742012,"pokeball":742011},
}
"""
s=replace_once(s,anchor,const+anchor,'audit MFB registry')

old="""                    set(VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS) | set(VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS) |
                    set(VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS) |
"""
new="""                    set(VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS) | set(VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS) |
                    set(VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS) | set(MFB_POKEBALL_EXACT_ROWS) |
"""
s=replace_once(s,old,new,'audit MFB live targets')

anchor='        exact_primary_worlds_pair = False\n'
evidence="""        exact_mfb_pokeball_pair = False
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

"""
s=replace_once(s,anchor,evidence+anchor,'audit MFB evidence')

anchor='        elif card_id in VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS:\n'
classification="""        elif card_id in MFB_POKEBALL_EXACT_ROWS:
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
"""
s=replace_once(s,anchor,classification+anchor,'audit MFB classification')

anchor='\ndef main():\n'
runtime="""
def runtime_mfb_pokeball_regression():
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
    js="\\n".join(extract_fn(n) for n in names if n!="tcgdexExactMfbPokeballPrice")+"\\n"+registry+"\\n"+extract_fn("tcgdexExactMfbPokeballPrice")
    harness=r'''\nconst fixtures=JSON.parse(process.argv[1]);\nconst rules=JSON.parse(process.argv[2]);\nfunction fail(m){throw new Error(m)}\nif(canonicalStamp('MFB Poké Ball')!=='MFB Poké Ball')fail('taxonomy not canonicalized');\nconst out={};\nfor(const [id,rule] of Object.entries(rules)){\n  const c=fixtures[id];\n  const ok=tcgdexExactMfbPokeballPrice(c,'Normal','MFB Poké Ball');\n  if(!ok||Number(ok.idProduct)!==Number(rule.pokeball))fail(id+' exact Poké Ball product mismatch');\n  if(tcgdexExactMfbPokeballPrice(c,'Holo','MFB Poké Ball')!==null)fail(id+' wrong finish accepted');\n  if(tcgdexExactMfbPokeballPrice(c,'Normal','None')!==null)fail(id+' None stamp accepted');\n  if(tcgdexExactMfbPokeballPrice({...c,localId:'999'},'Normal','MFB Poké Ball')!==null)fail(id+' wrong localId accepted');\n  out[id]=Number(ok.idProduct);\n}\nif(tcgdexExactMfbPokeballPrice(fixtures['mfb-9'],'Normal','MFB Poké Ball')!==null)fail('mfb-9 contaminated special row accepted');\nprocess.stdout.write(JSON.stringify(out));\n'''
    return json.loads(subprocess.check_output(["node","-e",js+"\\n"+harness,json.dumps(fixtures,ensure_ascii=False),json.dumps(MFB_POKEBALL_EXACT_ROWS)],text=True))

"""
s=replace_once(s,anchor,runtime+anchor,'audit MFB runtime regression')

old='    runtime_regression["swsh028GameStop"] = runtime_swsh028_gamestop_regression()\n'
new=old+'    runtime_regression["mfbPokeball"] = runtime_mfb_pokeball_regression()\n'
s=replace_once(s,old,new,'audit MFB runtime call')
p.write_text(s)
print('MFB Poké Ball production patch applied')
