#!/usr/bin/env python3
from pathlib import Path
import re, subprocess

ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/'index.html').read_text(encoding='utf-8')

def fn(name):
    marker="function "+name+"("
    start=SRC.find(marker)
    if start<0: raise AssertionError(f"missing {name}")
    b=SRC.find('{',start+len(marker)); depth=0; quote=None; esc=False
    for i in range(b,len(SRC)):
        ch=SRC[i]
        if quote:
            if esc: esc=False
            elif ch=='\\\\': esc=True
            elif ch==quote: quote=None
            continue
        if ch in ("'", '"', chr(96)): quote=ch
        elif ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0: return SRC[start:i+1]
    raise AssertionError(name)

names=['physicalCardIdentityKey','collectionIdentityKey','recordKey','legacyDeckRecordKey','deckRecordKey','findCardForDeckEntry','migrateLegacyDeckEntryKeys','deckEntryQty','allocatedInOtherDecks','availableForDeck']
code='\\n'.join(fn(n) for n in names)
code+=r'''
function normText(v){return String(v||'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
function canonicalVariant(v){return String(v||'Normal')}
function canonicalStamp(v){return String(v||'None')}
function normalizedPlaySeries(v){return String(v||'')}
const normal={id:'sv09-146',tcgdexId:'sv09-146',name:'Ricerca di Brock',localId:'146',set:'Avventure Insieme',variant:'Normal',stamp:'None',playSeries:'',language:'Italiano',condition:'NM',status:'Disponibile',qty:8};
const play={id:'sv09-146',tcgdexId:'sv09-146',name:'Ricerca di Brock',localId:'146',set:'Avventure Insieme',variant:'Normal',stamp:'Play! Pokémon',playSeries:'9',language:'Italiano',condition:'NM',status:'Disponibile',qty:1};
let db=[normal,play];
let decks=[{id:'psico',entries:[]}];
const legacyKey=recordKey(normal);
if(legacyKey!==recordKey(play))throw new Error('fixture must reproduce old collision');
decks[0].entries=[{cardKey:legacyKey,cardId:'sv09-146',variant:'Normal',qty:4}];
if(deckRecordKey(normal)===deckRecordKey(play))throw new Error('new keys still collide');
if(legacyDeckRecordKey(normal)!==legacyDeckRecordKey(play))throw new Error('legacy fixture no longer collides');
if(!migrateLegacyDeckEntryKeys())throw new Error('legacy entry was not migrated');
const migrated=decks[0].entries[0];
if(migrated.cardKey!==deckRecordKey(normal))throw new Error('legacy entry did not preserve old resolver target');
if(migrated.stamp!=='None')throw new Error('legacy normal entry got wrong stamp');
if(deckEntryQty(decks[0],deckRecordKey(normal))!==4)throw new Error('normal count wrong');
if(deckEntryQty(decks[0],deckRecordKey(play))!==0)throw new Error('Play count inherited normal count');
decks[0].entries.push({cardKey:deckRecordKey(play),cardId:play.id,variant:play.variant,stamp:play.stamp,playSeries:play.playSeries,qty:1});
if(deckEntryQty(decks[0],deckRecordKey(normal))!==4)throw new Error('normal count changed after Play add');
if(deckEntryQty(decks[0],deckRecordKey(play))!==1)throw new Error('Play count wrong after add');
if(availableForDeck(normal,decks[0])!==8)throw new Error('normal availability wrong');
if(availableForDeck(play,decks[0])!==1)throw new Error('Play availability wrong');
console.log(JSON.stringify({status:'PASS',normalQty:deckEntryQty(decks[0],deckRecordKey(normal)),playQty:deckEntryQty(decks[0],deckRecordKey(play)),normalKey:deckRecordKey(normal),playKey:deckRecordKey(play)}));
'''
r=subprocess.run(['node','-'],input=code,text=True,capture_output=True)
if r.returncode: raise AssertionError(r.stderr)
print(r.stdout.strip())
