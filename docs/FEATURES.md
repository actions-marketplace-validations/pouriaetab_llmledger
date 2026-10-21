# Everything llmledger does

The long list, one entry per feature, in the order they were added. The short version is in the [README](../README.md).

1. **Rebuilds the history.** Reads every version of
   `model_prices_and_context_window.json` that LiteLLM's `main` branch went
   through, in order, using git.
2. **Writes a change log.** Compares each version with the one before and records
   one row per change: a model added or removed, a price changed, a retirement
   date set (`data/events.csv`).
3. **Estimates competing risks.** Follows each newly added model until its first
   exit (a price change, a retirement announcement or removal) and estimates the
   chance of each with the Aalen-Johansen estimator and 95% bootstrap confidence
   intervals (`data/survival.csv`).
4. **Publishes the results.** Rebuilds the results page from LiteLLM's latest
   history every day (`site/index.html`).
5. **Looks up any model.** Search by name, maker or host, under LiteLLM's own
   names or grouped by model, to see each listing's chance of a price change in
   the next 90 days and year, its timeline and full outlook, and a side by side
   comparison of up to five models. The page also lists every change in the
   last 7 days and the most repriced models. Every table sorts, keeps its
   header in view and lets you move columns, and remembers all of it.
6. **Flags corrections.** Tags bulk clean ups (50 or more models removed on the
   same day), unit fixes (a price made 100 times larger or smaller), changes
   undone within 30 days and likely corrections (a price change in a model's
   first 7 days, from 0, or of 10 times or more), and shows the results with
   and without them.
7. **Checks itself in SQL.** Every run builds the table of models a second time
   in SQL (`survival.sql`, run with SQLite) and stops before publishing if SQL
   and Python disagree on any model.
8. **Prices a prompt.** Paste a prompt to see what it would cost on every listed
   model, cheapest first, next to each model's chance of a price change in the
   next 90 days. It covers text answers (with images, PDF pages, audio or video
   attached), and making images, video or speech. Filter by what a model must
   be able to do, and by maker, model, version and host. The prompt stays in
   your browser.
9. **Finds the best value for a task.** For 26 tasks, from coding, math and
   writing to 7 fields, 7 languages, images, documents and websites, it marks
   the cheapest model whose Arena rating cannot be told apart from the top
   model's.
10. **Guesses the task of a prompt.** From its words and attachments, in the
    browser, it guesses the task (coding, math, a field or a language) and
    picks the best value model for it. On 1,740 real Arena prompts kept apart
    from the ones used to write the rules, it picks one of the prompt's tasks
    69.7% of the time (67.5 to 71.8%), against 45.4% for always guessing
    Everything (overall).
11. **Checks licences every day.** Before building, it reads the current licence
    of every outside source. If one is no longer open for business use, it
    stops using it (or stops publishing, for the core data) and opens a GitHub
    issue.
12. **Compares models side by side.** Columns that follow the prompt (the
    three answers, or a Claude or ChatGPT plan's top rated models) plus up to
    three of your own: Arena rating and rank, effort levels with a suggested
    level, prices, answer tokens and cost per task, or how fast each uses the
    plan. It names the pick and says, for each other model, how few answer
    tokens it would need to cost the same.
13. **Works inside Claude.** The plug-in in `mcp/` (llmledger-mcp) answers the
    same questions inside Claude, Cursor or any app that speaks MCP, from the
    daily `data.json`. See [Use it inside Claude](../README.md#use-it-inside-claude).
14. **Replays the leaderboards.** The Trends view plays every past Arena
    leaderboard as a moving chart: the best closed model against the best
    open one (and how often people would pick the leader), the top 5 makers,
    and a price race: the top rated model's price, the cheapest of the top 10,
    and what a model as good as last year's #1 costs now, rebuilt from every
    price change in the catalogue. Next to it: the newest models with their
    best Arena rank, and the latest price changes and retirements.
15. **Shows cost against quality.** For your prompt, every rated model's cost
    against its Arena score, with the edge marked: the models no other model
    beats on both.
16. **One page when it fits, otherwise it scrolls.** The answers come first,
    the extras are tabs in one panel under them, shown at their full height,
    and a model's details open in a drawer. When a view has more than the
    window holds, the page scrolls the normal way: nothing is cut, squeezed
    into a box that scrolls inside, or shrunk to fit. About shows each part
    as a row that opens on a click.
17. **Measures how many price changes are corrections.** A labelled random
    sample of first price changes, with a written guide, shows how often the
    catalogue fixes its own entry instead of recording a real price change,
    and how well simple rules and a small model tell the two apart. See
    [How many first price changes are corrections?](../README.md#how-many-first-price-changes-are-corrections)
18. **Checks every build before it goes live.** A build that knows fewer
    models than the live page, lists a quarter fewer, or has older data is
    not published. When the data is 3 or more days old, the page and the
    plug-in say so, and a failed daily refresh opens an issue in this
    repository until a refresh passes again.
19. **Works as an Agent Skill too.** The folder `skills/llmledger` gives AI
    agents the plug-in's answers through a small script, standard library
    only. Until it is used, the skill takes about 150 tokens of an agent's
    context, against well over 1,000 for the plug-in's tools. See
    [Use it inside Claude](../README.md#use-it-inside-claude).
20. **Lists models seen but not yet priced.** New models on Arena that the
    catalogue has no price for, and how soon a model usually gets one after
    Arena first shows it, by maker (Price history, Not yet priced).
21. **Shows where each change came from.** Every change in a model's timeline
    links the LiteLLM change behind it, and the plug-in gives a model's prices
    on any past day with the change that set them. Estimates count cache reads
    and cache writes, and an answer from the offline copy says how old it is.
22. **Learns how long your jobs take.** The plug-in times a job (one call and
    the whole job, as a usual time and a slow day) from your own timed runs,
    kept on your computer, including promptfoo's results files; and promptfoo
    can check the plug-in's answers against the data. See
    [promptfoo.md](promptfoo.md).
23. **Quotes a whole job from a sample.** Run 20 of a job's tests in promptfoo,
    and the plug-in quotes the whole job on each model in it: time as a usual
    time and a slow day, cost at the cheapest listing next to the one used, the
    chance of a price change within 90 days, how often it was right with a 95%
    range, and what a wrong answer must cost for the dearer model to pay off.
24. **Local or cloud?** Pay a cloud model per call, or buy a computer and run
    an open model at home: the cost a month each way, the month the computer
    pays for itself, and whether it keeps up. The local model's speed comes from
    your own timed runs, electricity from the U.S. Energy Information
    Administration (public domain) or your own price, and the computer's price
    is yours.
25. **Your usage on other models.** Hand the plug-in your coding agent's own
    token export (`ccusage daily --json`, `ccusage session --json` or
    `codeburn export -f json`) and it prices the same work on every model
    rated for that kind of work, each session at the price of its day, with
    Arena ratings, the models that keep the rating and cost less, a 95% range
    for the cost per session, and whether two models differ for real or the
    data cannot tell. Token counts only; nothing leaves your computer.

