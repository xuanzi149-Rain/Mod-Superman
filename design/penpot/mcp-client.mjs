// Local design automation bridge; uses the SDK installed by the official Penpot MCP package.
import { pathToFileURL } from 'node:url';
import fs from 'node:fs/promises';
const sdk = 'C:/Users/17583/AppData/Local/npm-cache/_npx/3c82a6444c262e31/node_modules/@penpot/mcp/packages/server/node_modules/@modelcontextprotocol/sdk/dist/esm/client/';
const { Client } = await import(pathToFileURL(sdk + 'index.js'));
const { StreamableHTTPClientTransport } = await import(pathToFileURL(sdk + 'streamableHttp.js'));
const client = new Client({ name: 'mod-superman-design', version: '1.0.0' });
try {
  await client.connect(new StreamableHTTPClientTransport(new URL('http://localhost:4401/mcp')));
  const [command, file, member] = process.argv.slice(2);
  const request = command === 'api' ? {name:'penpot_api_info',arguments:{type:file,...(member?{member}:{})}} : ['exec','save-result'].includes(command) ? {name:'execute_code',arguments:{code:await fs.readFile(file,'utf8')}} : command === 'call' ? JSON.parse(await fs.readFile(file,'utf8')) : null;
  const result = command === 'list' ? await client.listTools() : await client.callTool(request, undefined, { timeout: 90000 });
  if(command==='save-result'){
    const payload=JSON.parse(result.content.find(c=>c.type==='text').text).result;
    if(!payload?.base64)throw Error('No export data: '+JSON.stringify(payload));
    await fs.writeFile(member,Buffer.from(payload.base64,'base64'));
    console.log(JSON.stringify({path:member,bytes:Buffer.from(payload.base64,'base64').length}));
  }else console.log(JSON.stringify(result));
} finally { await client.close(); }
