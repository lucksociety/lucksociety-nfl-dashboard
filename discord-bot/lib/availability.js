'use strict';
// Market-free live inputs. Depth charts are expected starters, not official game-day actives.
const BASE = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl';
const norm = s => String(s || '').toLowerCase().replace(/[^a-z]/g, '');
const unavailable = s => /^(out|inactive|injured reserve|suspension|suspended|reserve|physically unable)/i.test(s || '');
const uncertain = s => /questionable|doubtful/i.test(s || '');
const providerTeam = s => ({WAS:'wsh',LA:'lar',JAX:'jax',LV:'lv'}[s] || String(s).toLowerCase());
const cutoffDate = v => typeof v==='string' ? v : v?.last_game_date;
const alias = s => ({LAR:'LA',WSH:'WAS',JAC:'JAX',LVR:'LV'}[s] || s);
async function liveJSON(url) {
  const u = new URL(url); u.searchParams.set('_refresh', String(Date.now()));
  const r = await fetch(u, {cache:'no-store',headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(10000)});
  if (!r.ok) throw new Error(`availability HTTP ${r.status}`);
  return r.json();
}
function injuriesOf(body) {
  if (!Array.isArray(body?.injuries)) throw new Error('injury feed schema unavailable');
  const byTeam = {};
  for (const team of body.injuries) for (const x of team.injuries || []) {
    const a=x.athlete || {}, code=alias(a.team?.abbreviation);
    if (!code || !a.displayName) continue;
    (byTeam[code] ||= []).push({name:a.displayName,position:a.position?.abbreviation,status:x.status,updatedAt:x.date});
  }
  return byTeam;
}
function quarterbacks(body) {
  const chart=body?.depthchart;
  if(!Array.isArray(chart)) throw new Error('depth chart schema unavailable');
  return chart.flatMap(c=>Object.entries(c.positions||{}).filter(([key])=>key.toLowerCase()==='qb').flatMap(([,p])=>p.athletes||[]))
    .map(a=>({name:a.displayName,status:(a.injuries||[])[0]?.status||'listed'}));
}
function ratingFor(name, team, wk) {
  const n=norm(name), initial=n[0], surname=String(name).trim().split(/\s+/).pop().toLowerCase();
  const candidates=(wk.qbs||[]).filter(q=>q.team===team && (norm(q.name)===n || (norm(q.name).startsWith(initial)&&norm(q.name).endsWith(norm(surname)))));
  return candidates.length===1 ? candidates[0] : null;
}
async function refreshGames(games,wk,{fetchJSON=liveJSON,now=new Date(),dataThrough}={}) {
  const at=now.toISOString(),day=games[0]?.gameday;
  dataThrough=cutoffDate(dataThrough);
  let injuryBody,board,leagueError;
  try {[injuryBody,board]=await Promise.all([fetchJSON(BASE+'/injuries'),fetchJSON(BASE+'/scoreboard?dates='+day.replaceAll('-',''))]);}
  catch(e){leagueError=e.message;}
  let injuries={};try{injuries=injuriesOf(injuryBody);}catch(e){leagueError ||= e.message;}
  const teams=[...new Set(games.flatMap(g=>[g.away,g.home]))],depth={};
  await Promise.all(teams.map(async team=>{try{depth[team]=quarterbacks(await fetchJSON(`${BASE}/teams/${providerTeam(team)}/depthcharts`));}catch{depth[team]=null;}}));
  return games.map(original=>{
    const g=structuredClone(original),reasons=[];if(leagueError)reasons.push('live injury/schedule feed unavailable');
    const event=(board?.events||[]).find(e=>{const c=e.competitions?.[0]?.competitors||[];return c.some(x=>x.homeAway==='away'&&alias(x.team?.abbreviation)===g.away)&&c.some(x=>x.homeAway==='home'&&alias(x.team?.abbreviation)===g.home);});
    if(!event)reasons.push('current schedule not verified');
    else {
      const c=event.competitions?.[0],status=c?.status?.type||event.status?.type;g.liveStatus=status?.name;
      if(status?.state!=='pre')reasons.push('game is not pregame');
      const start=new Date(c?.date||event.date);
      if(Number.isFinite(+start)){
        const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(start).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
        const day=`${parts.year}-${parts.month}-${parts.day}`;
        if(day!==g.gameday)reasons.push('official game date changed; select the new date');
        g.gameday=day;g.gametime=`${parts.hour}:${parts.minute}`;
      }
    }
    const sides={};
    for(const side of ['away','home']){
      const team=g[side],rows=injuries[team]||[],qbs=depth[team];
      sides[side]={injuries:rows,quarterback:null};
      if(!qbs?.length){reasons.push(`${team} live QB depth chart unavailable`);continue;}
      const qb=qbs.find(q=>!unavailable(rows.find(x=>norm(x.name)===norm(q.name))?.status||q.status));
      if(!qb){reasons.push(`${team} available quarterback unknown`);continue;}
      const status=rows.find(x=>norm(x.name)===norm(qb.name))?.status||qb.status;
      sides[side].quarterback={name:qb.name,status,confirmation:'expected depth-chart starter'};
      if(uncertain(status))reasons.push(`${team} quarterback availability uncertain`);
      const listed=g.sides[side].qb_name;
      const samePerson = norm(listed)===norm(qb.name) || (listed && norm(listed).startsWith(norm(qb.name)[0]) && norm(listed).endsWith(norm(qb.name.split(" ").pop())));
      if(!samePerson){
        const q=ratingFor(qb.name,team,wk);
        if(q){g.sides[side].x.qb=q.r-(wk.mix[team]??wk.qb_prior);g.sides[side].qb_name=qb.name;g.sides[side].qb_id=q.id;sides[side].quarterback.changedFrom=listed;}
        else if(!(listed&&norm(listed).startsWith(norm(qb.name)[0])&&norm(listed).endsWith(norm(qb.name.split(' ').pop()))))reasons.push(`${team} current QB has no unique fitted player rating`);
      }
      // No invented point penalties for new non-QB absences the team-level model cannot price.
      const recent=rows.filter(x=>x.position!=='QB' && (unavailable(x.status)||uncertain(x.status)) && dataThrough && String(x.updatedAt||'').slice(0,10)>dataThrough);
      if(recent.length)reasons.push(`${team} recent non-QB availability changes need review: ${recent.slice(0,3).map(x=>x.name).join(', ')}`);
    }
    g.availability={checkedAt:at,source:'ESPN live injuries + team depth charts + scoreboard',sides,blockReason:reasons.join('; ')||null};
    return g;
  });
}
module.exports={liveJSON,injuriesOf,quarterbacks,ratingFor,refreshGames,providerTeam,cutoffDate};
