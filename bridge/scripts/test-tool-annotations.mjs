import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const serverPath = fileURLToPath(new URL("../dist/index.js", import.meta.url));
const transport = new StdioClientTransport({
  command: process.execPath,
  args: [serverPath],
});
const client = new Client({ name: "tool-annotations-test", version: "1.0.0" });

try {
  await client.connect(transport);
  const { tools } = await client.listTools();
  const missingAnnotations = tools.filter((tool) => !tool.annotations).map((tool) => tool.name);
  const readOnly = tools.filter((tool) => tool.annotations?.readOnlyHint);
  const mutating = tools.filter(
    (tool) => tool.annotations?.readOnlyHint === false && !tool.annotations?.destructiveHint,
  );
  const destructive = tools.filter((tool) => tool.annotations?.destructiveHint);

  assert.equal(tools.length, 54);
  assert.deepEqual(missingAnnotations, []);
  assert.equal(readOnly.length, 37);
  assert.equal(mutating.length, 16);
  assert.deepEqual(
    destructive.map((tool) => tool.name),
    ["patch_bytes"],
  );
} finally {
  await client.close();
}
