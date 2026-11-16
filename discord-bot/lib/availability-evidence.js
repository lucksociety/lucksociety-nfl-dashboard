'use strict';
const {key}=require('./player-identity');
const out=s=>/^(out|inactive|injured reserve|suspension|suspended|reserve|physically unable)/i.test(s||'');
function assess(row,evidence,{starter=false,gameDate}={}){
 const unknown=reason=>({name:row.name,decision:'unresolved',reason});
 if(row.identityConflict)return unknown('conflicting player identity/status');
 const games=evidence?.games||[];
 if(games.length<2||games.some(g=>!g.coverage||g.date>=gameDate))return unknown('prior participation coverage unavailable');
 const last=games.at(-1);
 if((Date.parse(gameDate+'T12:00Z')-Date.parse(last.date+'T12:00Z'))/86400000>21)return unknown('prior participation evidence stale');
 const matched=games.map(g=>g.players.filter(p=>key(p.name)===key(row.name)));
 if(matched.some(a=>a.length>1))return unknown('ambiguous prior player identity');
 const injuries=last.injuries.filter(p=>key(p.name)===key(row.name));
 if(injuries.length>1)return unknown('ambiguous prior injury identity');
 const lastTwo=matched.slice(-2);
 // Explicit previous out report + two covered games without participation establishes ongoing absence.
 if(out(row.status)&&injuries.length===1&&out(injuries[0].status)&&lastTwo.every(a=>a.length===0||a.every(p=>p.offense===0&&p.defense===0&&p.special===0)))
  return {name:row.name,decision:'ongoing_absence',reason:'Previously out and no participation in two prior covered games',priorGames:games.slice(-2).map(g=>g.id)};
 const appeared=matched.flat();
 if(!starter&&games.length===3&&appeared.length>=2&&appeared.every(p=>[p.offense,p.defense,p.special].every(v=>Number.isFinite(v)&&v>=0&&v<.10)))
  return {name:row.name,decision:'limited_role',reason:'Not a current depth-chart starter; below 10% in every snap category across three covered games',priorGames:games.map(g=>g.id)};
 return unknown(starter?'current depth-chart starter availability unresolved':'new, high-usage or unverified role change');
}
module.exports={assess};
