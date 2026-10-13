import { loadSyntheticEnv } from "../lib/env";
import { buildModelChain, fetchGatewayModels } from "../lib/llmModels";

loadSyntheticEnv();

const models = await fetchGatewayModels();
const pat = process.argv[2];
const ids = models.map((m) => m.id);
const shown = pat ? ids.filter((id) => new RegExp(pat, "i").test(id)) : ids;

console.log(`total=${ids.length}`);
for (const id of shown) {
  const m = models.find((x) => x.id === id);
  console.log(`${id}${m?.owned_by ? ` (${m.owned_by})` : ""}`);
}

const chain = buildModelChain(models, process.env.LLM_MODEL || process.env.SYNTHETIC_LLM_COMBO);
console.log("\nresolved chain:", chain.join(" → ") || "(none)");
