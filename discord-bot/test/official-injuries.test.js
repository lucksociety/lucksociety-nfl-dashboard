const assert=require('node:assert/strict');
const O=require('../lib/official-injuries'),A=require('../lib/availability');
const game={game_id:'g',away:'WAS',home:'NYG',gameday:'2026-11-12',gametime:'20:15',sides:{away:{qb_name:'Jayden Daniels',x:{qb:0}},home:{qb_name:'J.J. McCarthy',x:{qb:0}}}};
const wk={week:10,season:2026},now=new Date('2026-11-12T06:00:00Z');
function table(team,rows){return `<div class="nfl-o-injury-report__container"><img data-src="https://static.www.nfl.com/league/api/clubs/logos/${team}"><table><thead><tr>${['Player','Position','Injury','Mon','Tue','Wed','Game Status'].map(s=>'<th>'+s+'</th>').join('')}</tr></thead><tbody>${rows.map(([name,pos,status])=>'<tr>'+[name,pos,'','LP','FP','FP',status].map(s=>'<td>'+s+'</td>').join('')+'</tr>').join('')}</tbody></table></div>`;}
const html='"NflSeason":"2026"<select><option value="/week/REG-10" selected>WEEK 10</option></select>'+table('NYG',[['J.J. McCarthy','QB','(-)'],['Cam Skattebo','RB','(-)'],['Malik Harrison','LB','QUESTIONABLE']])+table('WSH',[['Jayden Daniels','QB','UNSPECIFIED'],['Treylon Burks','WR','UNSPECIFIED'],['Lucas Patrick','G','OUT']]);
const report=O.parse(html,game,10,2026,now);assert.equal(report.teams.NYG[0].status,'Active');assert.equal(report.teams.WAS.find(p=>p.name==='Lucas Patrick').status,'Out');
for(const [h,g,w,s,n]of [[html,game,9,2026,now],[html,game,10,2025,now],[html.replaceAll('Wed','Tue'),game,10,2026,now],[html,{...game,home:'BUF'},10,2026,now],[html.replace('QUESTIONABLE','SURPRISE'),game,10,2026,now],[html,game,10,2026,new Date('2026-11-11T18:00:00Z')]])assert.throws(()=>O.parse(h,g,w,s,n));
const provider={NYG:[{name:'J.J. McCarthy',position:'QB',status:'Questionable',updatedAt:'2026-11-10T21:00:00Z'},{name:'Cam Skattebo',position:'RB',status:'Out',updatedAt:'2026-11-10T21:00:00Z'}],WAS:[{name:'Treylon Burks',position:'WR',status:'Out',updatedAt:'2026-11-11T22:00:00Z'}]};
const fixed=O.reconcile(provider,report,game);assert.equal(fixed.corrections.length,3);assert.equal(fixed.injuries.NYG[0].status,'Active');assert.equal(provider.NYG[0].status,'Questionable','original source stays immutable');
const late=structuredClone(provider);late.NYG[0].updatedAt='2026-11-12T12:00:00Z';const conflict=O.reconcile(late,report,game);assert.equal(conflict.injuries.NYG[0].status,'Questionable');assert.match(conflict.conflicts.join(),/newer game-day/);
(async()=>{
 const fetchJSON=async url=>{
  if(url.includes('/injuries'))return {injuries:Object.entries(provider).map(([team,rows])=>({injuries:rows.map(r=>({athlete:{displayName:r.name,position:{abbreviation:r.position},team:{abbreviation:team}},status:r.status,date:r.updatedAt}))}))};
  if(url.includes('/scoreboard'))return {events:[{status:{type:{state:'pre'}},competitions:[{competitors:[{homeAway:'away',team:{abbreviation:'WSH'}},{homeAway:'home',team:{abbreviation:'NYG'}}]}]}]};
  const name=url.includes('/wsh/')?'Jayden Daniels':'J.J. McCarthy';return {depthchart:[{positions:{qb:{athletes:[{displayName:name,injuries:[{status:'Questionable'}]}]}}}]};
 };
 const officialLoader=async()=>({...report,sources:[{url:'https://www.giants.com/team/injury-report/',sha256:report.sha256}]});
 const [g]=await A.refreshGames([game],wk,{now,dataThrough:'2026-11-09',fetchJSON,officialLoader});
 assert(!g.availability.blockReason.includes('quarterback availability uncertain'),'official no-designation replaces stale depth-chart flag');
 assert(!g.availability.blockReason.includes('Treylon Burks'));assert(!g.availability.blockReason.includes('Cam Skattebo'));
 assert.match(g.availability.blockReason,/Lucas Patrick/);assert.match(g.availability.blockReason,/Malik Harrison/);
 assert.equal(g.availability.officialReport.corrections.length,3);
 const [fallback]=await A.refreshGames([game],wk,{now,dataThrough:'2026-11-09',fetchJSON,officialLoader:async()=>{throw Error('bad report')}});assert.match(fallback.availability.blockReason,/quarterback availability uncertain/);
 console.log('NFL official report identity/finality, stale provider reconciliation, late-scratch conflicts and genuine injury blocks: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
