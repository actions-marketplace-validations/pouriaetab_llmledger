// Assertions for tests.json: each reads the tool's JSON answer and compares it with the answer key that
// make_tests.py worked out from data.json (the test's "expected" value).
const body = output => {
  const list = typeof output === 'string' ? JSON.parse(output) : output;
  const item = Array.isArray(list) ? list.find(x => x.type === 'text') : list;
  return JSON.parse(item.text ?? JSON.stringify(item));
};
const near = (a, b) => Math.abs(a - b) <= 1e-9 + 1e-6 * Math.abs(b);
const verdict = (pass, reason) => ({ pass, score: pass ? 1 : 0, reason });

module.exports.perCall = (output, context) => {
  const want = Number(context.vars.expected);
  const got = body(output).models[0].per_call;
  return verdict(near(got, want), `per_call ${got}, cheapest listing ${want}`);
};
module.exports.listingsInTotal = (output, context) => {
  const want = Number(context.vars.expected);
  const got = body(output).listings_in_total;
  return verdict(got === want, `${got} listings, data.json has ${want}`);
};
module.exports.costPerTask = (output, context) => {
  const want = typeof context.vars.expected === 'string' ? JSON.parse(context.vars.expected) : context.vars.expected;
  const got = body(output).models.map(m => m.cost_per_task);
  return verdict(got.every((g, i) => near(g, want[i])), `cost_per_task ${got}, estimate_cost ${want}`);
};
module.exports.usageCost = (output, context) => {
  const want = typeof context.vars.expected === 'string' ? JSON.parse(context.vars.expected) : context.vars.expected;
  const row = body(output).every_model.find(m => m.model === want[0]);
  const got = row ? row.cost : null;
  return verdict(row !== undefined && near(got, want[1]), `${want[0]} cost ${got}, 5 x estimate_cost ${want[1]}`);
};
