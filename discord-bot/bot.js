#!/usr/bin/env node
/* Luck Society NFL Discord bot (gateway). /nfl [date] [game] -> v6 sims (100k each, seeded) -> Jupiter edges -> branded embeds.
 * Token comes ONLY from env DISCORD_BOT_TOKEN and is never logged. */
'use strict';
const { Client, GatewayIntentBits, Events, REST, Routes, ApplicationCommandOptionType, MessageFlags } = require('discord.js');
const { runNfl, UserError } = require('./lib/run');
const model = require('./lib/model');

const TOKEN = process.env.DISCORD_BOT_TOKEN;
const APP_ID = process.env.DISCORD_APP_ID || '1564884302297043014';
const redact = (s) => { let t = String(s); if (TOKEN) t = t.split(TOKEN).join('[REDACTED]'); return t.replace(/[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,40}/g, '[REDACTED]'); };
const log = (...a) => console.log(`${new Date().toISOString()} ${redact(a.map((x) => (x instanceof Error ? x.stack : typeof x === 'string' ? x : JSON.stringify(x))).join(' '))}`);
if (!TOKEN) { log('FATAL DISCORD_BOT_TOKEN is not set'); process.exit(78); }

const COMMANDS = [{
  name: 'nfl',
  description: 'Run the Luck Society NFL v6 sim (100k per game) + Jupiter best bet',
  dm_permission: true,
  options: [
    { type: ApplicationCommandOptionType.String, name: 'date', description: 'Game day YYYY-MM-DD (default: today ET, or the next game day)', required: false, max_length: 10 },
    { type: ApplicationCommandOptionType.String, name: 'game', description: 'Only one team, e.g. PHI', required: false, autocomplete: true, max_length: 4 },
  ],
}];

async function registerCommands() {
  const rest = new REST({ version: '10' }).setToken(TOKEN);
  const res = await rest.put(Routes.applicationCommands(APP_ID), { body: COMMANDS });
  log(`COMMANDS_REGISTERED global: ${res.map((c) => `/${c.name} (id ${c.id})`).join(', ')}`);
}

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
client.once(Events.ClientReady, async (c) => {
  log(`READY logged in as ${c.user.tag} (id ${c.user.id}) · guilds=${c.guilds.cache.size} · dashboard=${model.DASH}`);
  try { await registerCommands(); } catch (e) { log('COMMAND_REGISTER_FAILED', e.message || e); }
});
client.on(Events.GuildCreate, (g) => log(`GUILD_JOIN ${g.name} (${g.id})`));
client.on(Events.Error, (e) => log('CLIENT_ERROR', e.message || e));
client.on(Events.ShardDisconnect, (ev, id) => log(`SHARD_DISCONNECT shard=${id} code=${ev && ev.code}`));
client.on(Events.ShardResume, (id) => log(`SHARD_RESUME shard=${id}`));

let teamList = null;
async function teams() { if (!teamList) { const idx = await model.getJSON('index.json'); teamList = Object.entries(idx.teams).map(([ab, t]) => ({ ab, name: t.name })); } return teamList; }

client.on(Events.InteractionCreate, async (it) => {
  try {
    if (it.isAutocomplete() && it.commandName === 'nfl') {
      const q = String(it.options.getFocused() || '').toLowerCase();
      const list = (await teams()).filter((t) => !q || t.ab.toLowerCase().startsWith(q) || t.name.toLowerCase().includes(q)).slice(0, 25);
      return it.respond(list.map((t) => ({ name: `${t.ab} · ${t.name}`, value: t.ab })));
    }
    if (!it.isChatInputCommand() || it.commandName !== 'nfl') return;
    const date = it.options.getString('date') || undefined, game = it.options.getString('game') || undefined;
    const who = `${it.user.username}(${it.user.id}) in ${it.guildId || 'DM'}`;
    log(`CMD /nfl date=${date || '-'} game=${game || '-'} by ${who}`);
    await it.deferReply();
    const t0 = Date.now();
    let r;
    try { r = await runNfl({ date, game }); }
    catch (e) {
      if (e instanceof UserError) { log(`CMD_USER_ERROR ${e.message}`); return it.editReply({ content: `🍀 ${e.message}` }); }
      throw e;
    }
    await it.editReply({ embeds: r.messages[0] });
    for (const m of r.messages.slice(1)) await it.followUp({ embeds: m });
    log(`CMD_OK date=${r.date} moved=${r.moved} team=${r.team || '-'} games=${r.nGames} sim=${r.simMs}ms market=${r.mktMs}ms src=${r.marketSource || '-'}${r.marketError ? ' market_error=' + r.marketError : ''} total=${Date.now() - t0}ms`);
  } catch (e) {
    log('CMD_FAILED', e);
    try {
      const msg = { content: '🍀 Something went wrong running the sim. Try again in a minute.' };
      if (it.deferred || it.replied) await it.editReply(msg); else if (it.isRepliable()) await it.reply({ ...msg, flags: MessageFlags.Ephemeral });
    } catch (_) { /* ignore */ }
  }
});

process.on('unhandledRejection', (e) => log('UNHANDLED_REJECTION', e));
process.on('SIGTERM', () => { log('SIGTERM shutting down'); client.destroy().finally(() => process.exit(0)); });
process.on('SIGINT', () => { log('SIGINT shutting down'); client.destroy().finally(() => process.exit(0)); });

log('STARTING bot');
client.login(TOKEN).catch((e) => { log('LOGIN_FAILED', e.message || e); process.exit(1); });
