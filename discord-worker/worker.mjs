// Encrypt short-lived interaction credentials before putting them in public workflow inputs.
export async function dispatchModel(env, interaction, date, workflow, repo) {
  const app = env.DISCORD_APPLICATION_ID || interaction.application_id;
  const edit = async content => {
    const r = await fetch(`https://discord.com/api/v10/webhooks/${app}/${interaction.token}/messages/@original`, {
      method: 'PATCH', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ content, allowed_mentions: { parse: [] } }),
    });
    if (!r.ok) throw new Error(`Discord reply HTTP ${r.status}`);
  };
  try {
    if (!env.GITHUB_TOKEN || !env.RELAY_KEY) throw new Error('configure GITHUB_TOKEN and RELAY_KEY on the Worker, plus the same RELAY_KEY in Actions');
    const keyBytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(env.RELAY_KEY));
    const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['encrypt']);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const msg = { token: interaction.token, app, ts: Date.now(), date,
      only_bets: (interaction.data?.options || []).some(o => o.name === 'only_bets' && o.value === true) };
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(JSON.stringify(msg))));
    const bytes = new Uint8Array(iv.length + ct.length); bytes.set(iv); bytes.set(ct, iv.length);
    const relay = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO || repo}/actions/workflows/${workflow}/dispatches`, {
      method: 'POST', headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: 'application/vnd.github+json',
        'content-type': 'application/json', 'user-agent': 'oracle-discord', 'x-github-api-version': '2022-11-28' },
      body: JSON.stringify({ ref: env.GITHUB_REF || 'main', inputs: { date, relay } }),
    });
    if (r.status !== 204) throw new Error(`GitHub dispatch HTTP ${r.status}`);
    // The workflow owns the deferred reply from here. A progress PATCH here could race its result.
  } catch (e) {
    await edit(`⚠️ Could not start the model for ${date}: ${e.message}.`);
  }
}


const APP = '1564884302297043014';
const json = (data, status=200) => Response.json(data, {status});
export const todayET = (now=new Date()) => new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
export function validDate(date) {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(Date.parse(date+'T12:00:00Z')) && new Date(date+'T12:00:00Z').toISOString().slice(0,10) === date;
}
export function dateOptions(index, query='', today=todayET()) {
  const q=String(query).trim().toLowerCase();
  const dates=Object.keys(index.dates || {}).filter(validDate);
  const ordered=[...dates.filter(d=>d>=today).sort(),...dates.filter(d=>d<today).sort().reverse()];
  return ordered.filter(d=>!q || d.includes(q) || `week ${index.dates[d]}`.includes(q) || `w${index.dates[d]}`===q).slice(0,25).map(d=>({name:`${d} · Week ${index.dates[d]}${d===today?' · today':''}`,value:d}));
}
async function verify(request, publicKey) {
  const sig=request.headers.get('X-Signature-Ed25519') || '';
  const ts=request.headers.get('X-Signature-Timestamp') || '';
  const body=await request.text();
  if(!/^[a-f0-9]{128}$/i.test(sig) || !/^\d+$/.test(ts) || Math.abs(Date.now()/1000-Number(ts))>300 || !/^[a-f0-9]{64}$/i.test(publicKey || '')) return {ok:false,body};
  try {
    const bytes=hex=>Uint8Array.from(hex.match(/../g),v=>parseInt(v,16));
    const key=await crypto.subtle.importKey('raw',bytes(publicKey),'Ed25519',false,['verify']);
    return {ok:await crypto.subtle.verify('Ed25519',key,bytes(sig),new TextEncoder().encode(ts+body)),body};
  } catch { return {ok:false,body}; }
}
export default {
  async fetch(request,env,ctx) {
    const pathname=new URL(request.url).pathname;
    if(!['/','/interactions'].includes(pathname))return new Response('Not found',{status:404});
    if(request.method==='GET')return json({service:'nfl-oracle-discord',transport:'github-actions',application_id:APP});
    if(request.method!=='POST')return new Response('Method not allowed',{status:405});
    const checked=await verify(request,env.DISCORD_PUBLIC_KEY);
    if(!checked.ok)return new Response('Invalid signature',{status:401});
    let it;try {it=JSON.parse(checked.body);}catch{return new Response('Invalid JSON',{status:400});}
    if(it.type===1)return json({type:1});
    if(it.application_id!==APP)return new Response('Wrong application',{status:401});
    if(it.data?.name!=='nfl')return json({type:4,data:{content:'Unknown command.',flags:64}});
    if(it.type===4){
      try {
        const r=await fetch(`${env.DATA_URL || 'https://lucksociety.github.io/lucksociety-nfl-dashboard/data'}/index.json`,{signal:AbortSignal.timeout(1800)});
        if(!r.ok)throw new Error('Schedule unavailable');
        const query=(it.data.options || []).find(o=>o.name==='date')?.value || '';
        return json({type:8,data:{choices:dateOptions(await r.json(),query)}});
      }catch{return json({type:8,data:{choices:[]}});}
    }
    if(it.type!==2)return new Response('Unsupported interaction',{status:400});
    const date=String((it.data.options || []).find(o=>o.name==='date')?.value || todayET()).trim();
    if(!validDate(date))return json({type:4,data:{content:'Use a valid date in YYYY-MM-DD format.',flags:64}});
    if(!env.GITHUB_TOKEN || !env.RELAY_KEY)return json({type:4,data:{content:'NFL runner is not configured. Please contact the server administrator.',flags:64}});
    ctx.waitUntil(dispatchModel(env,it,date,'discord-nfl.yml','lucksociety/lucksociety-nfl-dashboard'));
    return json({type:5});
  }
};
