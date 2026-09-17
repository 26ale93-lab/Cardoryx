from pathlib import Path

INDEX = Path('index.html')
AUDIT = Path('scripts/test_card_identity_cardmarket_audit.py')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)


def patch_index():
    s = INDEX.read_text(encoding='utf-8')

    option = '<option value="30° Anniversario">30° Anniversario</option>'
    if s.count(option) != 2:
        raise SystemExit(f'30th option count: {s.count(option)}')
    worlds_options = option + '\n          <option value="Worlds 2022">Worlds 2022</option>\n          <option value="Worlds 2023">Worlds 2023</option>\n          <option value="Worlds 2024">Worlds 2024</option>'
    s = s.replace(option, worlds_options)

    old = "  if(n.includes('30 anniversario')||n.includes('30th celebration')||n.includes('30 celebration'))return '30° Anniversario';\n"
    new = old + "  if(n.includes('worlds2022'))return 'Worlds 2022';\n  if(n.includes('worlds2023'))return 'Worlds 2023';\n  if(n.includes('worlds2024'))return 'Worlds 2024';\n"
    s = replace_once(s, old, new, 'canonicalStamp')

    old = "    '30° Anniversario':['30thcelebration','30anniversario','30thanniversary'],\n"
    new = old + "    'Worlds 2022':['worlds2022'],\n    'Worlds 2023':['worlds2023'],\n    'Worlds 2024':['worlds2024'],\n"
    s = replace_once(s, old, new, 'stamp evidence')

    anchor = 'function cachedOfficialPlaySeries(card){\n'
    helper = """const VERIFIED_PRIMARY_WORLDS_STAMPS={
  'swshp-SWSH296':{setId:'swshp',localId:'SWSH296',name:'Champions Festival',stamp:'Worlds 2022',token:'worlds2022',productId:671798,staffProductId:672087},
  'svp-045':{setId:'svp',localId:'045',name:'Paradise Resort',stamp:'Worlds 2023',token:'worlds2023',productId:726924,staffProductId:727542},
  'svp-150':{setId:'svp',localId:'150',name:'Paradise Resort',stamp:'Worlds 2024',token:'worlds2024',productId:783445,staffProductId:783446}
};
function verifiedPrimaryWorldsStamp(card){
  const id=String(card?.tcgdexId||card?.id||'').trim();
  const rule=VERIFIED_PRIMARY_WORLDS_STAMPS[id];
  if(!rule||cardSetId(card)!==rule.setId||exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId)||normText(card?.name||'')!==normText(rule.name))return '';
  const topPid=Number(card?.pricing?.cardmarket?.idProduct||card?.pricing?.cardmarket?.id_product||0);
  if(topPid!==rule.productId)return '';
  const rows=tcgdexVariantDetails(card).filter(row=>{
    const stamps=(Array.isArray(row?.stamp)?row.stamp:[]).map(normText);
    const pid=Number(row?.thirdParty?.cardmarket||0),cm=row?.pricing?.cardmarket||{},ppid=Number(cm?.idProduct||cm?.id_product||0);
    const usable=['trend','avg7','avg30','avg','low'].some(k=>Number(cm?.[k]||0)>0);
    return stamps.length===1&&stamps[0]===rule.token&&canonicalFinishTypeLabel(row?.type)==='normal'&&!canonicalFinishFoilLabel(row?.foil)&&String(row?.size||'standard').trim().toLowerCase()==='standard'&&pid===rule.productId&&ppid===rule.productId&&usable;
  });
  return rows.length===1?rule.stamp:'';
}

"""
    s = replace_once(s, anchor, helper + anchor, 'Worlds helper')

    old = """  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){
    sel.value='30° Anniversario';
    const ps=document.getElementById(edit?'editPlaySeries':'playSeries');
    if(ps)ps.value='';
  }
"""
    new = old + """  const exactWorlds=verifiedPrimaryWorldsStamp(card);
  if(exactWorlds && canonicalStamp(sel.value||card?.stamp||'None')==='None'){
    sel.value=exactWorlds;
    const ps=document.getElementById(edit?'editPlaySeries':'playSeries');
    if(ps)ps.value='';
  }
"""
    s = replace_once(s, old, new, 'syncStampAvailability')

    anchor = 'function tcgdexExactSvpStampPrice(card,variant,stamp){\n'
    resolver = """function tcgdexExactWorldsStampPrice(card,variant,stamp){
  const id=String(card?.tcgdexId||card?.id||'').trim(),rule=VERIFIED_PRIMARY_WORLDS_STAMPS[id];
  if(!rule||cardSetId(card)!==rule.setId||exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId)||normText(card?.name||'')!==normText(rule.name)||canonicalVariant(variant||'Normal')!=='Normal')return null;
  const st=canonicalStamp(stamp);let expectedPid=0,expectedStamps=[];
  if(st===rule.stamp){expectedPid=rule.productId;expectedStamps=[rule.token];}
  else if(st==='Staff'){expectedPid=rule.staffProductId;expectedStamps=[rule.token,'staff'];}
  else return null;
  const expected=[...expectedStamps].sort();
  const rows=tcgdexVariantDetails(card).filter(row=>{
    const stamps=(Array.isArray(row?.stamp)?row.stamp:[]).map(normText).sort();
    const pid=Number(row?.thirdParty?.cardmarket||0),cm=row?.pricing?.cardmarket||{},ppid=Number(cm?.idProduct||cm?.id_product||0);
    const usable=['trend','avg7','avg30','avg','low'].some(k=>Number(cm?.[k]||0)>0);
    return stamps.length===expected.length&&stamps.every((v,i)=>v===expected[i])&&canonicalFinishTypeLabel(row?.type)==='normal'&&!canonicalFinishFoilLabel(row?.foil)&&String(row?.size||'standard').trim().toLowerCase()==='standard'&&pid===expectedPid&&ppid===expectedPid&&usable;
  });
  if(rows.length!==1)return null;
  const cm=rows[0].pricing.cardmarket;
  return {...cm,idProduct:expectedPid,source:`TCGdex · Cardmarket · ${st}`,verified:String(cm?.updated||'')};
}

"""
    s = replace_once(s, anchor, resolver + anchor, 'Worlds resolver')

    old = """  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
  if(swsh028GameStop)return swsh028GameStop;
  const tcgdexExact=tcgdexExactSvpStampPrice(card,variant,stamp);
"""
    new = """  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
  if(swsh028GameStop)return swsh028GameStop;
  const worldsExact=tcgdexExactWorldsStampPrice(card,variant,stamp);
  if(worldsExact)return worldsExact;
  const tcgdexExact=tcgdexExactSvpStampPrice(card,variant,stamp);
"""
    s = replace_once(s, old, new, 'stamp resolver chain')

    INDEX.write_text(s, encoding='utf-8')


def patch_audit():
    s = AUDIT.read_text(encoding='utf-8')
    anchor = 'VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS = {\n'
    const = """VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS = {
    "swshp-SWSH296": {"setId":"swshp","localId":"SWSH296","name":"Champions Festival","stamp":"worlds-2022","productId":671798,"staffProductId":672087},
    "svp-045": {"setId":"svp","localId":"045","name":"Paradise Resort","stamp":"worlds-2023","productId":726924,"staffProductId":727542},
    "svp-150": {"setId":"svp","localId":"150","name":"Paradise Resort","stamp":"worlds-2024","productId":783445,"staffProductId":783446},
}
"""
    s = replace_once(s, anchor, const + anchor, 'audit constant')

    old = '                    set(VERIFIED_STANDARD_JUMBO_CARDMARKET_PAIRS) | set(VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS) |\n'
    new = old + '                    set(VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS) |\n'
    s = replace_once(s, old, new, 'audit live targets')

    anchor = '        exact_primary_special_pair = False\n'
    block = """        exact_primary_worlds_pair = False
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

"""
    s = replace_once(s, anchor, block + anchor, 'audit Worlds evidence')

    anchor = '        elif card_id in VERIFIED_PRIMARY_SPECIAL_CARDMARKET_ROWS:\n'
    block = """        elif card_id in VERIFIED_PRIMARY_WORLDS_CARDMARKET_ROWS:
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
"""
    s = replace_once(s, anchor, block, 'audit Worlds classification')

    anchor = '            "verifiedPrimarySpecialPair": exact_primary_special_pair,\n'
    new = '            "verifiedPrimaryWorldsPair": exact_primary_worlds_pair,\n            "verifiedPrimaryWorldsProducts": exact_primary_worlds_products,\n' + anchor
    s = replace_once(s, anchor, new, 'audit report fields')

    AUDIT.write_text(s, encoding='utf-8')


patch_index()
patch_audit()
print('Exact Worlds patch applied')
