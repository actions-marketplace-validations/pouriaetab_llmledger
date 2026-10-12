# Scope and disclaimer

llmledger is a statistics and engineering project. It studies the public change
history of one open source file, LiteLLM's model price catalogue, to show how a
data pipeline, a specification, automated tests and a survival analysis fit
together.

1. **Not financial, procurement, legal or tax advice.** Nothing here is advice
   on which model or provider to use, or on what any model costs you. The author
   is not a financial adviser and does not act as one.
2. **Catalogue edits, not provider prices.** Every number describes edits to
   LiteLLM's `model_prices_and_context_window.json`: when an entry was added,
   when its listed price changed, when a retirement date was set, and when it was
   removed. A provider can change its real price before, after or without such
   an edit.
3. **No orders, no strategy.** The code reads a public git history and writes
   CSV files. It buys nothing, calls no paid service and contains no strategy.
4. **No performance claims.** Past patterns in the catalogue say nothing certain
   about future changes. The confidence intervals describe sampling uncertainty
   only.
5. **Independent.** The data comes from the MIT licensed BerriAI/litellm
   repository. This project is not affiliated with or endorsed by BerriAI or
   LiteLLM.
6. **No liability.** The software and documentation are provided "as is",
   without warranty of any kind (see [LICENSE](LICENSE)). The author accepts no
   liability for any loss or damage, financial or otherwise, arising from any use
   of this repository or of anything derived from it. Anyone who uses it does so
   at their own risk.