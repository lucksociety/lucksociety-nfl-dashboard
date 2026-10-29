// No external data or Discord traffic in command pipeline regression tests.
process.env.NFL_DATA_URL = '';
globalThis.fetch = async () => new Response(JSON.stringify({ data: [], pagination: { hasNext: false } }), { status: 200, headers: { 'content-type': 'application/json' } });
