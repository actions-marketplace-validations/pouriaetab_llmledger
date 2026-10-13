/* llmledger prompt cost: small pure functions used by the page (app.js)
   and checked by tests/test_cost.py. No page code here. */
(function (root) {
  const CHARS_PER_TOKEN = 4;             // a common rule of thumb for English text
  const TEXT_MODES = ["chat", "responses", "completion"];
  // LiteLLM lists a few embedding and image models as chat; leave those out by name.
  const NOT_TEXT = /embed|rerank|flux|diffusion|sdxl|controlnet|dall-e|imagen|whisper|tts/;

  function isTextModel(key, mode) {
    return TEXT_MODES.includes(mode) && !NOT_TEXT.test(String(key).toLowerCase());
  }

  // Estimated tokens in a piece of text: characters / 4, rounded up.
  function estimateTokens(text) {
    return Math.ceil(Array.from(String(text || "")).length / CHARS_PER_TOKEN);
  }

  // Dollars for one call. Prices are dollars per 1M tokens; null if either is unknown.
  function costOf(inputPerM, outputPerM, inTokens, outTokens) {
    if (inputPerM == null || outputPerM == null) return null;
    return (inTokens * inputPerM + outTokens * outputPerM) / 1e6;
  }

  // Keep the cheapest row in each group, then sort all rows from cheapest up.
  function cheapestPerGroup(rows, groupOf, costOfRow) {
    const best = new Map();
    for (const row of rows) {
      const id = groupOf(row), cost = costOfRow(row);
      if (cost == null) continue;
      const kept = best.get(id);
      if (!kept || cost < kept.cost) best.set(id, { row, cost, id });
    }
    return [...best.values()].sort((a, b) => a.cost - b.cost || (a.id < b.id ? -1 : 1));
  }

  const api = { CHARS_PER_TOKEN, TEXT_MODES, isTextModel, estimateTokens, costOf, cheapestPerGroup };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LLMCOST = api;
})(this);
