/* llmledger prompt cost: small pure functions used by the page (app.js)
   and checked by tests/test_cost.py. No page code here. */
(function (root) {
  const CHARS_PER_TOKEN = 4;             // a common rule of thumb for English text
  const TEXT_MODES = ["chat", "responses", "completion"];
  // LiteLLM lists a few embedding and image models as chat; leave those out by name.
  const NOT_TEXT = /embed|rerank|flux|diffusion|sdxl|controlnet|dall-e|imagen|whisper|tts/;

  // Answer lengths, in output tokens.
  const ANSWERS = {
    short: { tokens: 250, label: "Short: a paragraph" },
    medium: { tokens: 800, label: "Medium: about a page" },
    long: { tokens: 2000, label: "Long: a long answer or a code file" },
    very_long: { tokens: 6000, label: "Very long: a report or a big code change" },
  };

  // Tokens for things attached to a prompt, used when LiteLLM has no
  // per-image or per-second price for the model. Rough, and they vary by model.
  const MEDIA_TOKENS = {
    image: 1000,          // one photo or screenshot of about 1,000 x 1,000 pixels
    page: 1500,           // one PDF page with text and images
    audioSecond: 32,      // one second of audio
    videoSecond: 300,     // one second of video with its sound
    imageOut: 1056,       // one generated 1,024 x 1,024 image, medium quality
  };
  const SPEECH_CHARS_PER_SECOND = 15;    // about 150 words a minute

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

  const first = (...values) => values.find(v => v != null) ?? null;

  // Dollars for one call of model m, or null when m cannot do it or has no price.
  // m: { key, mode, input, output (dollars per 1M tokens), skills: [...], media: {...} }
  // q: { want: "text" | "image" | "video" | "speech", inTok, outTok,
  //      images, pages, audioSeconds, videoSeconds, count }
  function priceFor(m, q) {
    const md = m.media || {}, skills = m.skills || [];
    const perToken = m.input == null ? null : m.input / 1e6;
    const prompt = perToken == null ? 0 : (q.inTok || 0) * perToken;
    if (q.want === "image") {
      if (m.mode !== "image_generation") return null;
      const size = String(m.key).match(/(\d+)-x-(\d+)/);
      const pixels = size ? Number(size[1]) * Number(size[2]) : null;
      const each = first(md.out_img, md.in_img,
        md.out_img_tok == null ? null : MEDIA_TOKENS.imageOut * md.out_img_tok,
        pixels && md.px_out != null ? pixels * md.px_out : null,
        pixels && md.px_in != null ? pixels * md.px_in : null);
      return each == null ? null : prompt + (q.count || 0) * each;
    }
    if (q.want === "video") {
      if (m.mode !== "video_generation") return null;
      const each = first(md.out_s, md.out_vid_s, md.out_s_720, md.out_s_1080, md.out_s_480);
      return each == null ? null : (q.count || 0) * each;
    }
    if (q.want === "speech") {
      if (m.mode !== "audio_speech") return null;
      const chars = q.count || 0;
      if (md.in_chr != null) return chars * md.in_chr;
      if (md.out_s != null) return (chars / SPEECH_CHARS_PER_SECOND) * md.out_s;
      return null;
    }
    if (!isTextModel(m.key, m.mode)) return null;
    let cost = costOf(m.input, m.output, q.inTok || 0, q.outTok || 0);
    if (cost == null) return null;
    if (q.images > 0) {
      if (!skills.includes("vision")) return null;
      cost += q.images * first(md.in_img, MEDIA_TOKENS.image * first(md.in_img_tok, perToken));
    }
    if (q.pages > 0) {
      if (!skills.includes("pdf")) return null;
      cost += q.pages * MEDIA_TOKENS.page * perToken;
    }
    if (q.audioSeconds > 0) {
      if (!skills.includes("audio")) return null;
      cost += q.audioSeconds * first(md.aud_s, MEDIA_TOKENS.audioSecond * first(md.aud_tok, perToken));
    }
    if (q.videoSeconds > 0) {
      if (!skills.includes("video")) return null;
      cost += q.videoSeconds * first(md.vid_s, MEDIA_TOKENS.videoSecond * first(md.vid_tok, perToken));
    }
    return cost;
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

  // Split a grouped name into a family and its version numbers, by naming rules:
  // "claude-sonnet-4.5" -> ["claude-sonnet", "4.5"], "qwen3.8-max" -> ["qwen-max", "3.8"].
  function familyOf(name) {
    const family = [], version = [];
    for (const part of String(name).split("-")) {
      const glued = part.match(/^([a-z]+)(\d[\w.]*)$/);
      if (/^v?\d/.test(part)) version.push(part);
      else if (glued && glued[1].length > 1) { family.push(glued[1]); version.push(glued[2]); }
      else family.push(part);
    }
    return [family.join("-") || String(name), version.join(" ")];
  }

  // Best value: the cheapest model whose 95% range overlaps the top model's.
  // rows: [{ rating, low, high, cost }] with cost != null.
  function bestValue(rows) {
    if (!rows.length) return null;
    const top = rows.reduce((a, b) => (b.rating > a.rating ? b : a));
    const tied = rows.filter(r => r.high >= top.low);
    return tied.reduce((a, b) => (b.cost < a.cost ? b : a));
  }

  const api = { CHARS_PER_TOKEN, TEXT_MODES, ANSWERS, MEDIA_TOKENS, SPEECH_CHARS_PER_SECOND,
    isTextModel, estimateTokens, costOf, priceFor, cheapestPerGroup, familyOf, bestValue };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LLMCOST = api;
})(this);
