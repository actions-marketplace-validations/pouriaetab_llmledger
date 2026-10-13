/* llmledger task guess: reads a prompt and guesses which Arena task it is,
   so the Best value tab can pick a model for it. Simple word rules, run in the
   browser: free, instant, and nothing is sent anywhere. How often the guess is
   right is measured on real Arena prompts by route_eval.py. */
(function (root) {
  // Each task: words that point to it. A match on a "strong" pattern counts 2.
  const TASKS = {
    webdev: {
      strong: /\b(html|css|tailwind|react|next\.js|nextjs|vue|svelte|landing page|web ?page|website|web app|frontend|front-end)\b/i,
      weak: /\b(navbar|button|layout|responsive|dom|jsx|tsx)\b/i,
    },
    coding: {
      strong: /```|\b(python|javascript|typescript|java|c\+\+|c#|golang|rust|kotlin|swift|flutter|php|ruby|bash|powershell|sql|regex|numpy|pandas|pytorch|tensorflow|django|flask|fastapi|node\.?js|npm|docker\w*|kubernetes|git|github|api|json|yaml|code|coding|script|function|debug|refactor|compile\w*|stack ?trace|traceback|exception|bug|algorithm|leetcode|unit test|programm\w*|linux|ubuntu|terminal|excel formula|vba)\b|(\bdef |\bimport |console\.log|#include|public static|=>|!=|==|\w+\(\)\s*[{;:]|[{};]\s*$|\bSELECT\b[\s\S]*\bFROM\b)|(код|программ|функци|скрипт|代码|程序|函数|编程|コード|プログラム|関数|코드|프로그램|함수|programowa\w*|\bkod\w*|funkcj\w*|código|programa\w*|fonction|Programmier\w*|پایتون|کد)/im,
      weak: /\b(variable|loop|array|class|method|library|install\w*|error|server|database|query|plugin|app|framework|sdk|cpu|gpu|windows|version|command|config\w*|network|router)\b/i,
    },
    math: {
      strong: /\b(solve|equation|integral|derivative|prove|proof|theorem|lemma|probability|calculus|algebra|geometry|matrix|matrices|eigen\w*|polynomial|logarithm|factorial|combinatorics|arithmetic)\b|\\(frac|int|sum|sqrt)|\d\s*[\^×÷]\s*\d|\b\d+\s*[+\-*\/]\s*\d+\s*=/i,
      weak: /\b(calculate|compute|how many|how long|percent\w*|average|mean|median|standard deviation|variance|sum of|formula|area of|volume of|limit|next number|x\s*=|f\(x\))\b|\d+\s*%|(\d+\s*,\s*){3,}|(数学|方程|计算|概率|確率|計算|수학|방정식|matemat\w*|oblicz\w*|równani\w*|вычисл\w*|уравнени\w*|задач\w*)/i,
    },
    creative_writing: {
      strong: /\b(story|stories|poem|poetry|lyrics|song|novel|fiction|fanfic\w*|screenplay|script for a|haiku|limerick|sonnet|fairy tale|roleplay|role-play|role play|role playing)\b|(小说|故事|诗|歌词|рассказ|стих\w*|песн\w*|сказк\w*|opowiada\w*|wiersz\w*|piosenk\w*|histoire|poème|chanson|Geschichte|Gedicht|cuento|poema|canción|小説|物語|이야기|소설)/i,
      weak: /\b(character|plot|chapter|scene|scenario|imagine|creative|narrat\w*|villain|hero|speech|toast|slogan)\b/i,
    },
    legal: { strong: /\b(lawsuit|attorney|lawyer|contract|legal|statute|court|plaintiff|defendant|gdpr|liabilit\w*|clause)\b/i,
      weak: /\b(law|rights|regulation|compliance|tenant|landlord)\b/i },
    medicine: { strong: /\b(symptom\w*|diagnos\w*|medication|dosage|clinical|patient|disease|treatment|doctor|surgery|pregnan\w*|vaccine)\b/i,
      weak: /\b(health|pain|medical|drug|therapy|blood|nutrition)\b/i },
    business: { strong: /\b(marketing|revenue|profit|startup|business plan|investor|pricing strategy|sales funnel|kpi|roi|invoice|accounting|financial statement|stock market|valuation)\b/i,
      weak: /\b(business|customer|budget|finance|company|market|sales|brand|product)\b/i },
    science: { strong: /\b(physics|chemistry|biology|molecule|quantum|thermodynamic\w*|photosynthesis|dna|genome|neuron|astronom\w*|hypothesis|experiment)\b/i,
      weak: /\b(atom|energy|cell|evolution|climate|species|planet|element)\b/i },
    writing: { strong: /\b(essay|proofread|rewrite|rephrase|paraphrase|summari[sz]e|grammar|cover letter|resume|email to|draft an? (email|letter))\b/i,
      weak: /\b(email|letter|article|blog|tone|wording|sentence|paragraph)\b/i },
    media: { strong: /\b(movie|film|tv show|series|anime|manga|album|football|soccer|basketball|nba|nfl|olympic\w*|video game|celebrity)\b/i,
      weak: /\b(music|sport\w*|game|actor|singer|team|season|episode)\b/i },
  };
  // Names to show for each task; the same tasks as arena.py's TASKS.
  const LABELS = {
    overall: "Everything (overall)",
    coding: "Coding",
    math: "Math",
    creative_writing: "Creative writing",
    instruction_following: "Following detailed instructions",
    hard_prompts: "Hard prompts",
    longer_query: "Long prompts",
    multi_turn: "Long conversations",
    expert: "Expert questions",
    business: "Business and finance",
    legal: "Legal and government",
    medicine: "Medicine and health",
    science: "Science",
    software: "Software and IT",
    writing: "Writing and literature",
    media: "Entertainment, sports and media",
    chinese: "In Chinese",
    french: "In French",
    german: "In German",
    japanese: "In Japanese",
    korean: "In Korean",
    russian: "In Russian",
    spanish: "In Spanish",
    vision: "Understanding images",
    document: "Understanding documents",
    webdev: "Building websites and apps"
  };
  // When two tasks tie, the first in this list wins.
  const ORDER = ["webdev", "coding", "math", "creative_writing", "legal", "medicine",
    "science", "business", "writing", "media"];

  // Languages that have their own Arena task, by writing system or common words.
  const LANGUAGES = [
    ["japanese", /[぀-ヿ]/],                  // hiragana or katakana
    ["korean", /[가-힯]/],                    // hangul
    ["chinese", /[一-鿿]/],                   // Chinese characters (checked after Japanese)
    ["russian", /[Ѐ-ӿ]/],                   // Cyrillic
    ["spanish", /[ñ¿¡]|\b(el|los|las|que|por|para|una|con|del|es|está|cómo|qué|puedes|necesito)\b/i],
    ["french", /[çœ]|\b(les|des|est|une|pour|dans|avec|qui|pas|je|vous|c'est|n'est|qu'il)\b/i],
    ["german", /ß|\b(der|die|das|und|ist|nicht|mit|ein|eine|ich|sie|auf|für|über|wie|bitte)\b/i],
  ];
  const ENGLISH = /\b(the|and|is|are|to|of|you|what|how|with|for|this|that|in)\b/gi;
  const SCRIPTS = ["japanese", "korean", "chinese", "russian"];

  // Writing systems decide Japanese, Korean, Chinese and Russian. Spanish, French
  // and German need at least 3 of their common words, and more than English ones.
  function language(text) {
    const english = (text.match(ENGLISH) || []).length;
    let best = null;
    for (const [name, pattern] of LANGUAGES) {
      const hits = (text.match(new RegExp(pattern.source, pattern.flags + "g")) || []).length;
      if (SCRIPTS.includes(name)) { if (hits >= 5) return name; continue; }
      if (hits >= 3 && hits > english && (!best || hits > best[1])) best = [name, hits];
    }
    return best ? best[0] : null;
  }

  function score(text, rule) {
    const found = [];
    let points = 0;
    for (const [pattern, weight] of [[rule.strong, 2], [rule.weak, 1]]) {
      for (const m of text.matchAll(new RegExp(pattern.source, pattern.flags + "g"))) {
        points += weight;
        if (found.length < 4 && !found.includes(m[0].trim().toLowerCase())) found.push(m[0].trim().toLowerCase());
      }
    }
    return { points, found };
  }

  // Guess the task of a prompt. extra: { images, pages } attached to it.
  // Returns { task, why: [...words or reasons], language }.
  function guessTask(text, extra) {
    text = String(text || "");
    extra = extra || {};
    if (extra.pages > 0) return { task: "document", why: ["a PDF is attached"], language: language(text) };
    if (extra.images > 0) return { task: "vision", why: ["an image is attached"], language: language(text) };
    let best = null;
    for (const task of ORDER) {
      const s = score(text, TASKS[task]);
      if (s.points >= 2 && (!best || s.points > best.points)) best = { task, ...s };
    }
    const lang = language(text);
    if (best) return { task: best.task, why: best.found, language: lang };
    if (lang) return { task: lang, why: ["written in " + lang[0].toUpperCase() + lang.slice(1)], language: lang };
    return { task: "overall", why: ["no clear task"], language: lang };
  }

  const api = { TASKS, ORDER, LABELS, guessTask, language };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LLMROUTE = api;
})(this);
