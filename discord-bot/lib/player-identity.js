'use strict';
// Full names only: terminal generational suffixes are aliases, never initial/surname fuzzy matches.
const key=name=>String(name||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\b(jr|sr|ii|iii|iv|v)\.?\s*$/i,'').replace(/[^a-z]/g,'');
function dedupe(rows){
 const result=[];
 for(const row of rows){
  const found=result.find(p=>key(p.name)===key(row.name)&&(!p.playerId||!row.playerId||p.playerId===row.playerId));
  if(!found){result.push({...row});continue;}
  // Conflicting duplicate flags remain visible; never silently turn an out into active.
  if(found.status!==row.status)found.identityConflict=true;
  if(Date.parse(row.updatedAt)>Date.parse(found.updatedAt))Object.assign(found,{...row,identityConflict:found.identityConflict});
 }
 return result;
}
module.exports={key,dedupe};
