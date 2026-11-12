// User-supplied starters are scenario annotations, never official health clearance.
'use strict';
function attach(games,document,{now=Date.now()}={}){
 if(document?.schema!==1||!Number.isFinite(Date.parse(document.expires_at))||now>=Date.parse(document.expires_at))return games;
 return games.map(g=>{
  const row=document.games?.[g.game_id];
  if(!row||document.date!==g.gameday||row.away!==g.away||row.home!==g.home)return g;
  if(!['away','home'].every(side=>Array.isArray(row.sides?.[side])&&row.sides[side].length===7&&row.sides[side].every(p=>['QB','RB','WR','TE','K'].includes(p.position)&&typeof p.name==='string'&&p.name.length>0&&p.name.length<80)))return g;
  return {...g,expectedLineup:{source:document.source,sourceReference:document.source_reference,expiresAt:document.expires_at,sides:structuredClone(row.sides),healthConfirmed:false}};
 });
}
module.exports={attach};
