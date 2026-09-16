const assert=require('assert');
const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync('index.html','utf8');
const a=source.indexOf('const VERIFIED_MCDONALDS_2021_CARDMARKET_PRODUCTS=');
const b=source.indexOf('function cardmarketValueForCardVariant',a);
assert(a>=0&&b>a,'McDonalds registry/resolver missing');
const block=source.slice(a,b);
const sandbox={};
sandbox.normText=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
sandbox.exactLocalIdKey=v=>{const raw=String(v??'').trim().toUpperCase().replace(/^0+(?=\d)/,'');return /^\d+$/.test(raw)?String(Number(raw)):raw};
sandbox.canonicalVariant=v=>{const x=sandbox.normText(v);if(x==='holo'||x==='holofoil')return 'Holo';if(x==='reverse'||x==='reverse holo'||x==='reverse holofoil')return 'Reverse Holo';return 'Normal'};
vm.createContext(sandbox);
vm.runInContext(block+'\nthis.resolve=verifiedMcdonalds2021CardmarketVariant; this.registry=VERIFIED_MCDONALDS_2021_CARDMARKET_PRODUCTS;',sandbox);
const expected=[
[1,'Bulbasaur',538778,.66,538783,3.71],[2,'Chikorita',538788,.28,538793,1.67],[3,'Treecko',538798,.21,538803,2.77],
[4,'Turtwig',538808,.20,538813,1.64],[5,'Snivy',538818,.20,538823,1.55],[6,'Chespin',538828,.24,538833,1.22],
[7,'Rowlet',538838,.18,538843,1.22],[8,'Grookey',538848,.15,538853,.89],[9,'Charmander',538858,.74,538863,4.22],
[10,'Cyndaquil',538868,.22,538873,1.62],[11,'Torchic',538878,.23,538883,1.19],[12,'Chimchar',538888,.25,538893,1.37],
[13,'Tepig',538898,.21,538903,1.09],[14,'Fennekin',538908,.18,538913,1.09],[15,'Litten',538918,.23,538923,1.15],
[16,'Scorbunny',538928,.24,538933,1.04],[17,'Squirtle',538938,.20,538943,4.34],[18,'Totodile',538948,.35,538953,1.87],
[19,'Mudkip',538958,.35,538963,1.62],[20,'Piplup',538968,.28,538973,2.77],[21,'Oshawott',538978,.18,538983,1.86],
[22,'Froakie',538988,.26,538993,1.10],[23,'Popplio',538998,.23,539003,3.90],[24,'Sobble',539008,.21,539013,2.64],
[25,'Pikachu',539018,2.03,539023,16.09]
];
assert.strictEqual(Object.keys(sandbox.registry).length,25);
for(const [n,name,np,nt,hp,ht] of expected){
  const card={id:`2021swsh-${n}`,tcgdexId:`2021swsh-${n}`,name,localId:String(n),set:{id:'2021swsh',name:"McDonald's Collection 2021"}};
  const normal=sandbox.resolve(card,'Normal');
  const holo=sandbox.resolve(card,'Holo');
  assert.strictEqual(normal?.matched,true,`${name} Normal not matched`);
  assert.strictEqual(normal.productId,np,`${name} Normal product`);
  assert.strictEqual(normal.pricing.trend,nt,`${name} Normal trend`);
  assert.strictEqual(holo?.matched,true,`${name} Holo not matched`);
  assert.strictEqual(holo.productId,hp,`${name} Holo product`);
  assert.strictEqual(holo.pricing.trend,ht,`${name} Holo trend`);
  assert.strictEqual(sandbox.resolve(card,'Reverse Holo')?.matched,false,`${name} Reverse must fail closed`);
  assert.strictEqual(sandbox.resolve({...card,name:name+' X'},'Normal')?.matched,false,`${name} wrong name must fail`);
  assert.strictEqual(sandbox.resolve({...card,localId:String(n+100)},'Normal')?.matched,false,`${name} wrong number must fail`);
  assert.strictEqual(sandbox.resolve({...card,set:{id:'other'}},'Normal')?.matched,false,`${name} wrong set must fail`);
}
// Explicit source-corruption recoveries demonstrated by the official catalogue.
assert.strictEqual(sandbox.resolve({id:'2021swsh-5',tcgdexId:'2021swsh-5',name:'Snivy',localId:'5',set:{id:'2021swsh'}},'Normal').productId,538818);
assert.strictEqual(sandbox.resolve({id:'2021swsh-16',tcgdexId:'2021swsh-16',name:'Scorbunny',localId:'16',set:{id:'2021swsh'}},'Normal').productId,538928);
assert.strictEqual(sandbox.resolve({id:'2021swsh-21',tcgdexId:'2021swsh-21',name:'Oshawott',localId:'21',set:{id:'2021swsh'}},'Holo').productId,538983);
assert(source.includes('const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);'),'value resolver integration missing');
assert(source.indexOf('const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);')!==source.lastIndexOf('const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);'),'stats resolver integration missing');
console.log('McDonalds 2021 runtime regression PASS: 25 identities / 50 exact finish products');
