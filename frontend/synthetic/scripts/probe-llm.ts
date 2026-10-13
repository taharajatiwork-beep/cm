import { loadSyntheticEnv } from "../lib/env";
import { chatCompletionsWithFallback, getModelChain } from "../lib/llmModels";

loadSyntheticEnv();

const chain = await getModelChain();
console.log("chain:", chain.length ? chain.join(" → ") : "(empty — set LLM_MODEL in .env)");

const res = await chatCompletionsWithFallback({
  max_tokens: 32,
  temperature: 0,
  messages: [{ role: "user", content: 'Reply JSON only: {"ok":true}' }],
  response_format: { type: "json_object" },
});

if (res.ok) {
  console.log("ok model=", res.model);
  console.log(res.content.slice(0, 200));
} else {
  console.log("fail", res);
  process.exit(1);
}
