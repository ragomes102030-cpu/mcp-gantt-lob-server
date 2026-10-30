// Independent remote MCP interoperability: official TypeScript client v2.
// No authentication or project write operations; synthetic calculation only.
import assert from 'node:assert/strict';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const targets = {
  eap: process.env.EAP_PUBLIC_MCP_URL,
  cronograma: process.env.CRONOGRAMA_PUBLIC_MCP_URL,
  gantt_lob: process.env.GANTT_LOB_PUBLIC_MCP_URL,
};
const cases = {
  eap: {
    tool: 'validar_estrutura_eap',
    args: { nos: [{ eap_id: '1', parent_id: null, nivel: 1 }] },
    field: 'ok', expected: true,
    names: ['avaliar_evidencia_eap', 'validar_estrutura_eap'],
  },
  cronograma: {
    tool: 'calcular_duracao_com_evidencia',
    args: { quantidade: 12, produtividade: 3, unidade: 'm2', unidade_produtividade: 'm2' },
    field: 'duracaoDias', expected: 4,
    names: ['calcular_cpm_com_evidencia', 'calcular_duracao_com_evidencia'],
  },
  gantt_lob: {
    tool: 'dimensionar_equipes_lob',
    args: { tempo_unitario: 6, ritmo_desejado: 2 },
    field: 'numero_equipes', expected: 3,
    names: ['balancear_ritmos_lob', 'calcular_linha_balanco', 'dimensionar_equipes_lob', 'listar_temas'],
  },
};
function decode(result) {
  assert.notEqual(result.isError, true, 'MCP tool returned isError');
  if (result.structuredContent !== undefined) {
    const value = result.structuredContent;
    return value?.result ?? value;
  }
  const block = result.content?.find((item) => item.type === 'text');
  assert.ok(block, 'MCP response without text/structuredContent');
  const json = JSON.parse(block.text);
  return json?.result ?? json;
}
for (const [name, url] of Object.entries(targets)) {
  assert.ok(url, 'Missing ' + name + ' endpoint');
  const testcase = cases[name];
  for (const mode of ['auto', 'legacy']) {
    const client = new Client(
      { name: 'arquimedes-typescript-independent-smoke', version: '1.0.0' },
      { versionNegotiation: { mode } },
    );
    try {
      await client.connect(new StreamableHTTPClientTransport(new URL(url)));
      const era = client.getProtocolEra();
      assert.equal(era, mode === 'auto' ? 'modern' : 'legacy', name + ' wrong protocol era');
      const { tools } = await client.listTools();
      const names = tools.map((tool) => tool.name).sort();
      assert.deepEqual(names, [...testcase.names].sort(), name + ' unexpected public tool names');
      const result = decode(await client.callTool({ name: testcase.tool, arguments: testcase.args }));
      assert.equal(result[testcase.field], testcase.expected, name + ' incorrect calculation');
      assert.equal(result.persistido, false, name + ' unexpected persistence');
      console.log(JSON.stringify({ sdk: 'mcp-typescript-v2', server: name, mode, era,
        tools: names, case: testcase.tool, result: result[testcase.field] }));
    } finally {
      await client.close();
    }
  }
}
