'use strict';
const {createHash}=require('node:crypto');
const DOMAINS={ARI:'azcardinals.com',ATL:'atlantafalcons.com',BAL:'baltimoreravens.com',BUF:'buffalobills.com',CAR:'panthers.com',CHI:'chicagobears.com',CIN:'bengals.com',CLE:'clevelandbrowns.com',DAL:'dallascowboys.com',DEN:'denverbroncos.com',DET:'detroitlions.com',GB:'packers.com',HOU:'houstontexans.com',IND:'colts.com',JAX:'jaguars.com',KC:'chiefs.com',LA:'therams.com',LAC:'chargers.com',LV:'raiders.com',MIA:'miamidolphins.com',MIN:'vikings.com',NE:'patriots.com',NO:'neworleanssaints.com',NYG:'giants.com',NYJ:'newyorkjets.com',PHI:'philadelphiaeagles.com',PIT:'steelers.com',SEA:'seahawks.com',SF:'49ers.com',TB:'buccaneers.com',TEN:'tennesseetitans.com',WAS:'commanders.com'};
const aliases={WSH:'WAS',LAR:'LA',JAC:'JAX',LVR:'LV'};
const text=s=>s.replace(/<[^>]*>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&').replace(/&#39;|&apos;/g,"'").replace(/&quot;/g,'"').replace(/\s+/g,' ').trim();
function finalDay(game){
 const d=new Date(game.gameday+'T12:00:00Z'),dow=d.getUTCDay();d.setUTCDate(d.getUTCDate()-(dow===4?1:2));return d;
}
function parse(html,game,week,season,now=new Date()){
 if(!Number.isInteger(week)||!Number.isInteger(season))throw Error('Official report season/week unavailable');
 const selected=[...html.matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/gi)].find(x=>/\bselected\b/i.test(x[1]));
 if(!selected||!new RegExp('REG-'+week+'(?:["\'/]|$)').test(selected[1])||!new RegExp('"NflSeason"\\s*:\\s*"?'+season+'"?').test(html))throw Error('Official report season/week mismatch');
 const day=finalDay(game),finalName=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][day.getUTCDay()];
 // Final reports normally arrive before 8pm ET; never treat earlier blank statuses as clearance.
 const et=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(now).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
 const currentDay=`${et.year}-${et.month}-${et.day}`,expectedDay=day.toISOString().slice(0,10);
 if(currentDay<expectedDay||(currentDay===expectedDay&&+et.hour<20)||currentDay>game.gameday)throw Error('Final-report publication window not verified');
 const teams={};
 for(const block of html.split(/<div\b[^>]*class="[^"]*nfl-o-injury-report__container[^"]*"[^>]*>/i).slice(1)){
  const table=/<table\b[^>]*>([\s\S]*?)<\/table>/i.exec(block);if(!table)continue;
  const logo=/api\/clubs\/logos\/([A-Z]+)/.exec(block.slice(0,block.indexOf('<table')));if(!logo)continue;
  const code=aliases[logo[1]]||logo[1];if(![game.home,game.away].includes(code)||teams[code])throw Error('Official report team identity ambiguous');
  const headers=[...table[1].matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/gi)].map(m=>text(m[1]));
  if(headers[0]!=='Player'||headers[1]!=='Position'||headers.at(-1)!=='Game Status'||headers.at(-2)!==finalName)throw Error('Final official report columns unavailable');
  const rows=[];
  for(const row of table[1].matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)){
   const cells=[...row[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(m=>text(m[1]));if(!cells.length)continue;
   if(cells.length!==headers.length||!cells[0])throw Error('Incomplete official injury row');
   const raw=cells.at(-1).toUpperCase(),status=({'OUT':'Out','DOUBTFUL':'Doubtful','QUESTIONABLE':'Questionable','(-)':'Active','-':'Active','UNSPECIFIED':'Active','':'Active'})[raw];
   if(!status)throw Error('Unknown official injury designation');
   rows.push({name:cells[0],position:cells[1],status,designation:status==='Active'?'No game designation':status,finalPractice:cells.at(-2)});
  }
  if(!rows.length)throw Error('Empty official injury table');teams[code]=rows;
 }
 if(!teams[game.home]||!teams[game.away])throw Error('Official report does not cover both teams');
 return {teams,week,season,finalReportDate:expectedDay,fetchedAt:now.toISOString(),sha256:createHash('sha256').update(html).digest('hex')};
}
async function liveText(url){const r=await fetch(url+'?_refresh='+Date.now(),{cache:'no-store',headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('Official report HTTP '+r.status);return r.text();}
async function load(game,wk,{fetchText=liveText,now=new Date()}={}){
 const urls=[game.home,game.away].map(t=>DOMAINS[t]).filter(Boolean).map(d=>'https://www.'+d+'/team/injury-report/');
 const results=await Promise.allSettled(urls.map(async url=>({...parse(await fetchText(url),game,wk.week,wk.season,now),url})));
 const reports=results.filter(r=>r.status==='fulfilled').map(r=>r.value);if(!reports.length)throw Error('No verified final official report');
 const norm=s=>s.toLowerCase().replace(/[^a-z]/g,'');
 for(const team of [game.home,game.away])for(const r of reports.slice(1)){
  if(r.teams[team].length!==reports[0].teams[team].length)throw Error('Official team reports differ in coverage');
  for(const p of reports[0].teams[team]){
  const q=r.teams[team].find(x=>norm(x.name)===norm(p.name));if(!q||q.status!==p.status)throw Error('Official team reports conflict');
 }
 }
 return {...reports[0],sources:reports.map(r=>({url:r.url,sha256:r.sha256,fetchedAt:r.fetchedAt}))};
}
module.exports={parse,load,liveText};

function reconcile(provider,report,game){
 const norm=s=>String(s||'').toLowerCase().replace(/[^a-z]/g,'');
 const result=structuredClone(provider),corrections=[],conflicts=[];
 for(const team of [game.home,game.away]){
  const rows=result[team]||=[];
  for(const official of report.teams[team]){
   const matches=rows.filter(p=>norm(p.name)===norm(official.name));
   if(matches.length>1)throw Error('Ambiguous official/provider player identity');
   const old=matches[0];
   if(old&&official.status==='Active'&&/out|questionable|doubtful|reserve/i.test(old.status)){
    const stamp=Date.parse(old.updatedAt),day=Number.isFinite(stamp)?new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(stamp):null;
    // Preserve a possible game-day scratch until the conflicting sources resolve it.
    if(day&&day>=game.gameday){conflicts.push(team+' '+old.name+' has a newer game-day provider flag');continue;}
    corrections.push({team,name:old.name,from:old.status,to:official.designation});
   }
   const row={...(old||{}),...official,providerStatus:old?.status||null,source:'official final team report',updatedAt:old?.updatedAt||report.finalReportDate+'T23:59:59Z'};
   if(old)rows[rows.indexOf(old)]=row;else rows.push(row);
  }
 }
 return {injuries:result,corrections,conflicts};
}
module.exports.reconcile=reconcile;
