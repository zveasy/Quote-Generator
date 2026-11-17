const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    n / 100,
  );
const dollars = (n) => (n === undefined || n === "" ? "" : Number(n) / 100);
const cents = (v) => Math.round((Number(v) || 0) * 100);
const disclaimer =
  "This estimate is not a confirmed booking. Services are subject to availability and final confirmation following the Meet & Greet process. Pricing and service details may be revised if the requested services or circumstances change.";
let state,
  current,
  mode = "login",
  account = "",
  editPrice,
  historical;
const view = (html) => {
  $("#view").innerHTML = html;
  $("#printout").innerHTML = "";
  message("");
};
function message(msg, error = false) {
  const el = $("#message");
  el.textContent = msg;
  el.className = error ? "error" : "notice";
  if (error) el.scrollIntoView();
}
function button(label, action, secondary = false, val = "") {
  return (
    '<button type="button" data-action="' +
    action +
    '" data-val="' +
    esc(val) +
    '" class="' +
    (secondary ? "secondary" : "primary") +
    '">' +
    esc(label) +
    "</button>"
  );
}
function field(label, name, val = "", type = "text", attrs = "") {
  return (
    "<label>" +
    esc(label) +
    '<input name="' +
    name +
    '" type="' +
    type +
    '" value="' +
    esc(val) +
    '" ' +
    attrs +
    "></label>"
  );
}
function area(label, name, val = "") {
  return (
    "<label>" +
    esc(label) +
    '<textarea name="' +
    name +
    '">' +
    esc(val) +
    "</textarea></label>"
  );
}
function select(label, name, options, val) {
  return (
    "<label>" +
    esc(label) +
    '<select name="' +
    name +
    '">' +
    options
      .map(
        ([id, text]) =>
          '<option value="' +
          esc(id) +
          '" ' +
          (id === val ? "selected" : "") +
          ">" +
          esc(text) +
          "</option>",
      )
      .join("") +
    "</select></label>"
  );
}
function block(title, content) {
  return (
    '<section class="card"><h2>' +
    esc(title) +
    '</h2><div class="grid">' +
    content +
    "</div></section>"
  );
}
function hero(kicker, title) {
  return (
    '<div class="hero"><span class="eyebrow">' +
    esc(kicker) +
    "</span><h1>" +
    esc(title) +
    "</h1></div>"
  );
}
const formData = () => Object.fromEntries(new FormData($("#view form")));
async function api(op, data = {}) {
  const r = await fetch("/api/" + op, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const b = await r.json();
  if (!r.ok) {
    if (r.status === 401 && state) {
      state = null;
      auth();
    }
    throw Error(b.error || "Request failed.");
  }
  return b;
}
async function load() {
  state = await api("home");
}
const admin = () => state.user.role === "Administrator";
const sender = () => admin() || state.user.canSend;
function nav(active) {
  $("nav").innerHTML = [
    "Quotes",
    ...(admin() ? ["Pricing", "Team"] : []),
    "My account",
    "Sign out",
  ]
    .map(
      (x) =>
        '<button data-action="' +
        {
          Quotes: "home",
          Pricing: "prices",
          Team: "team",
          "My account": "account",
          "Sign out": "logout",
        }[x] +
        '" ' +
        (x === active ? 'aria-current="page"' : "") +
        ">" +
        x +
        "</button>",
    )
    .join("");
}
function auth() {
  $("nav").innerHTML = '<span class="badge">Team workspace</span>';
  const titles = {
    login: "Welcome back.",
    signup: "Create your account.",
    confirm: "Verify your email.",
  };
  view(
    '<section class="auth"><div class="auth-art"><span class="eyebrow">Pawsitive Impact Pet Care</span><h2>Quote Studio</h2></div><div class="auth-form"><span class="eyebrow">Team access</span><h1>' +
      titles[mode] +
      "</h1><p>" +
      {
        login: "Sign in to prepare and manage client estimates.",
        signup: "Use the email your administrator approved.",
        confirm: "Enter the verification code sent to your inbox.",
      }[mode] +
      '</p><form class="stack" id="auth">' +
      (mode === "signup"
        ? field(
            "Full name",
            "name",
            "",
            "text",
            'required maxlength="100" autocomplete="name"',
          )
        : "") +
      field(
        "Email address",
        "email",
        account,
        "email",
        'required autocomplete="email"',
      ) +
      (mode === "confirm"
        ? field(
            "Verification code",
            "code",
            "",
            "text",
            'required autocomplete="one-time-code"',
          )
        : field(
            "Password",
            "password",
            "",
            "password",
            'required autocomplete="' +
              (mode === "login" ? "current-password" : "new-password") +
              '"',
          )) +
      "<button>" +
      { login: "Sign in", signup: "Sign up", confirm: "Verify email" }[mode] +
      '</button></form><div class="actions">' +
      (mode === "login"
        ? button("Sign up", "mode", true, "signup") +
          button("Verify email", "mode", true, "confirm")
        : button("Back to sign in", "mode", true, "login")) +
      (mode === "confirm" ? button("Resend code", "resend", true) : "") +
      "</div></div></section>",
  );
}
function statusName(s) {
  return s === "Accepted" ? "Accepted · Proceed to Meet & Greet" : s;
}
function rows(filter = "") {
  let list = state.quotes.filter((q) =>
    [q.id, q.fields.client, q.fields.email, q.fields.ttp, q.status]
      .join(" ")
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  return list.length
    ? "<table><thead><tr><th>Prospect</th><th>Estimate</th><th>Status</th><th>Total</th></tr></thead><tbody>" +
        list
          .map(
            (q) =>
              "<tr><td>" +
              button(q.fields.client || "Unnamed draft", "open", true, q.id) +
              "</td><td>" +
              esc(q.id) +
              " · v" +
              q.revision +
              '</td><td><span class="badge">' +
              esc(statusName(q.status)) +
              "</span></td><td>" +
              (q.estimate ? money(q.estimate.total) : "—") +
              "</td></tr>",
          )
          .join("") +
        "</tbody></table>"
    : "<p>No matching quotes.</p>";
}
function home() {
  current = null;
  nav("Quotes");
  view(
    hero("Quote Studio", "Client estimates") +
      '<section class="card"><div class="actions">' +
      button("Create a quote", "new") +
      (admin() && state.stats
        ? button("Export quote counts to S3", "stats", true)
        : "") +
      "</div>" +
      field(
        "Find a client or quote",
        "search",
        "",
        "search",
        'placeholder="Name, email, TTP ID or quote number"',
      ) +
      '<div id="rows" class="tablewrap">' +
      rows() +
      "</div></section>",
  );
}
function editor(q) {
  nav("Quotes");
  current = q;
  const f = q?.fields || {};
  view(
    hero(
      q ? q.id + " · Version " + q.revision : "Quote Studio",
      q ? "Edit draft" : "New estimate",
    ) +
      '<form class="stack" id="quote">' +
      block(
        "Client details",
        field("Client name", "client", f.client) +
          field("Email", "email", f.email, "email") +
          field("Phone", "phone", f.phone, "tel") +
          field("Service address", "address", f.address) +
          field("Time To Pet prospect / client ID", "ttp", f.ttp),
      ) +
      block(
        "Care request",
        select(
          "Service and pricing plan",
          "planId",
          [
            ["", "Choose a plan"],
            ...state.plans.map((p) => [
              p.planId,
              p.category +
                " · " +
                p.name +
                " · " +
                money(p.base) +
                (p.sheet && p.unit === "hour"
                  ? " first hour"
                  : p.sheet && p.unit === "chaperone-hour"
                    ? " / hour for one"
                    : " / " + p.unit),
            ]),
          ],
          f.planId,
        ) +
          field("Start date", "start", f.start, "date") +
          field("End date", "end", f.end, "date") +
          '<div id="serviceInputs" class="grid"></div>' +
          area("Pet types and household details", "petDetails", f.petDetails) +
          '<p id="planinfo" class="notice"></p>',
      ) +
      block(
        "Notes and adjustments",
        area("Client-facing notes / special requests", "notes", f.notes) +
          area("Internal notes", "internal", f.internal) +
          (admin()
            ? field(
                "Manual adjustment ($, negative for discount)",
                "adjustment",
                dollars(f.adjustment),
                "number",
                'step=".01"',
              ) + field("Adjustment reason shown to client", "reason", f.reason)
            : ""),
      ) +
      '<div id="calc"></div><div class="actions"><button>Save draft</button>' +
      button("Calculate estimate", "calculate", true) +
      (sender() && q ? button("Review and issue", "issue", true) : "") +
      (q ? button("History", "history", true) : "") +
      button("Back to quotes", "home", true) +
      "</div></form>",
  );
  planInfo(f);
}
function visitRow(value = "") {
  return (
    '<div class="actions">' +
    field("Visit start (local time)", "visitStart", value, "datetime-local") +
    button("Remove visit", "removevisit", true) +
    "</div>"
  );
}
function serviceInputs(p, f) {
  if (!p) return "";
  if (!p.sheet)
    return (
      field(
        "Visits or hours (nights calculated from dates)",
        "quantity",
        f.quantity,
        "number",
        'step=".01" min="0"',
      ) +
      field("Number of pets", "pets", f.pets, "number", 'min="1"') +
      field(
        "Number of chaperones for wedding care",
        "chaperones",
        f.chaperones ?? 1,
        "number",
        'min="1"',
      ) +
      field(
        "Travel distance (miles)",
        "miles",
        f.miles,
        "number",
        'min="0" step=".01"',
      ) +
      field("Optional add-on quantity", "extras", f.extras, "number", 'min="0"')
    );
  const count = (label, name, def, min = 0) =>
    field(label, name, f[name] ?? def, "number", 'step="1" min="' + min + '"');
  let html = count("Total pets", "pets", "", 1);
  if (p.unit !== "chaperone-hour")
    html += count("Travel from caretaker’s home (minutes)", "drive", "");
  if (p.unit === "visit") {
    const times = (f.visits || "").split("\n");
    html +=
      '<div><div id="visitRows">' +
      times.map(visitRow).join("") +
      "</div>" +
      button("Add visit", "addvisit", true) +
      "</div>";
  } else if (p.unit === "night") {
    html += count("Dogs", "dogs", 0) + count("Cats", "cats", 0);
    for (const [key, label] of [
      ["smallCare", "Small animal care"],
      ["chickenCare", "Chicken care"],
    ]) {
      html += select(
        label,
        key,
        [
          ["no", "No"],
          ["yes", "Yes"],
        ],
        f[key] || "no",
      );
    }
  } else {
    html += field(
      "Service hours",
      "quantity",
      f.quantity,
      "number",
      'min="2" step=".01"',
    );
    if (p.unit === "chaperone-hour")
      html += select(
        "Chaperones",
        "chaperones",
        [
          ["1", "1"],
          ["2", "2"],
        ],
        String(f.chaperones || 1),
      );
  }
  return html;
}
function planInfo(f = {}) {
  const p = state.plans.find((p) => p.planId === $("[name=planId]").value);
  $("#serviceInputs").innerHTML = serviceInputs(p, f);
  $("#planinfo").textContent = p
    ? [
        p.description,
        p.minutes ? p.minutes + " min" : "",
        p.addonName ? "Add-on: " + p.addonName + " · " + money(p.addon) : "",
      ]
        .filter(Boolean)
        .join(" · ")
    : "A pricing plan is required to issue an estimate.";
}
function quoteData() {
  const fields = formData();
  if ($("#visitRows")) {
    fields.visits = [...document.querySelectorAll("[name=visitStart]")]
      .map((x) => x.value)
      .join("\n");
    delete fields.visitStart;
  }
  fields.adjustment = cents(fields.adjustment);
  return { id: current?.id, version: current?.version || 0, fields };
}
function table(e) {
  return (
    '<div class="tablewrap"><table><thead><tr><th>Service or fee</th><th>Units</th><th>Rate</th><th>Amount</th></tr></thead><tbody>' +
    e.items
      .map(
        (i) =>
          "<tr><td>" +
          esc(i.label) +
          "</td><td>" +
          esc(i.units) +
          "</td><td>" +
          money(i.rate) +
          "</td><td>" +
          money(i.amount) +
          "</td></tr>",
      )
      .join("") +
    "</tbody></table></div><p>Service subtotal " +
    money(e.subtotal) +
    " · Fees " +
    money(e.fees) +
    " · Adjustments " +
    money(e.adjustment) +
    "</p><h3>Estimated total " +
    money(e.total) +
    "</h3>"
  );
}
function careSummary(q) {
  const f = q.fields,
    unit = q.pricing.unit;
  const duration =
    unit === "visit"
      ? (q.pricing.sheet ? q.estimate.items[0].units : f.quantity) +
        " visits of " +
        q.pricing.minutes +
        " minutes"
      : unit === "chaperone-hour"
        ? f.quantity + " hours × " + f.chaperones + " chaperones"
        : unit === "night"
          ? q.estimate.items[0].units + " nights"
          : f.quantity + " hours";
  return duration + " · " + f.pets + (Number(f.pets) === 1 ? " pet" : " pets");
}
function documentView(q) {
  const f = q.fields;
  return (
    '<article class="card estimate"><div class="brand"><img src="/logo.svg" alt=""><span>Pawsitive Impact Pet Care<small>Client estimate</small></span></div><h2>' +
    esc(f.client) +
    "</h2><p>" +
    esc(q.id) +
    " · Version " +
    q.revision +
    "<br>Issued " +
    esc(q.issued) +
    " · Valid through " +
    esc(q.expires) +
    "</p><p>" +
    esc(f.start) +
    " through " +
    esc(f.end) +
    "<br>" +
    esc(f.address) +
    "</p><h3>" +
    esc(q.pricing.category) +
    " · " +
    esc(q.pricing.name) +
    "</h3><p>" +
    esc(q.pricing.description) +
    "<br>" +
    esc(careSummary(q)) +
    "</p>" +
    table(q.estimate) +
    "<p>" +
    esc(f.notes) +
    "</p><h3>Next steps</h3><p>Reply to " +
    esc(q.pricing.contact) +
    " to request a Meet &amp; Greet or decline this estimate.</p><small>" +
    disclaimer +
    "</small></article>"
  );
}
function detail(q, readonly = false) {
  current = q;
  nav("Quotes");
  view(
    hero(q.id + " · Version " + q.revision, statusName(q.status)) +
      (q.estimate
        ? documentView(q)
        : '<section class="card"><h2>Draft snapshot</h2>' +
          Object.entries(q.fields)
            .map(([k, v]) =>
              v ? "<p>" + esc(k) + " · " + esc(v) + "</p>" : "",
            )
            .join("") +
          "</section>") +
      '<div class="actions">' +
      (q.estimate
        ? button("Print / Save PDF", "print") +
          button("Copy email estimate", "copy", true)
        : "") +
      (!readonly && sender() && q.status === "Issued"
        ? button("Mark as sent", "sent", true)
        : "") +
      (!readonly && sender() && q.status === "Sent"
        ? button("Record acceptance", "accept", true) +
          button("Record decline", "decline", true)
        : "") +
      (!readonly ? button("Create revision", "revise", true) : "") +
      button("History", "history", true) +
      button("Back to quotes", "home", true) +
      "</div>",
  );
  if (q.estimate) $("#printout").innerHTML = documentView(q);
}
function prices(p = null) {
  nav("Pricing");
  editPrice = p;
  const a = p || {};
  const num = (title, k, usd = false) =>
    field(
      title,
      k,
      usd ? dollars(a[k]) : a[k],
      "number",
      'min="0" step="' + (usd ? ".01" : "1") + '"',
    );
  view(
    hero("Administration", "Pricing catalog") +
      '<section class="card"><h2>Pricing versions</h2>' +
      (state.prices.length
        ? state.prices
            .slice()
            .sort((a, b) => b.created.localeCompare(a.created))
            .map(
              (x) =>
                "<p>" +
                button(x.name + " · " + x.effective, "editprice", true, x.id) +
                " " +
                money(x.base) +
                " / " +
                esc(x.unit) +
                "</p>",
            )
            .join("")
        : "<p>Add your first approved rate to enable quoting.</p>") +
      '</section><form id="price" class="stack">' +
      (p?.sheet
        ? block(
            "New version of " + p.name,
            field("Service name", "name", p.name, "text", "required") +
              area("Description and inclusions", "description", p.description) +
              field("Reply contact", "contact", p.contact, "text", "required") +
              field(
                "Effective from",
                "effective",
                p.effective,
                "date",
                "required",
              ) +
              num(
                {
                  visit: "Local rate per visit",
                  hour: "Local first hour",
                  night: "Base rate per night",
                  "chaperone-hour": "One chaperone per hour",
                }[p.unit] + " ($)",
                "base",
                true,
              ) +
              Object.entries(p.rates)
                .map(([key, value]) =>
                  field(
                    state.rateLabels[key] + " ($)",
                    "rate_" + key,
                    dollars(value),
                    "number",
                    'min="0" step=".01" required',
                  ),
                )
                .join(""),
          )
        : block(
            p ? "New version of " + p.name : "New pricing plan",
            field(
              "Category",
              "category",
              a.category,
              "text",
              'list="categories" required',
            ) +
              '<datalist id="categories">' +
              [
                "Check-in visits",
                "Overnight care",
                "Extended care",
                "Wedding chaperoning",
              ]
                .map((x) => "<option>" + x + "</option>")
                .join("") +
              "</datalist>" +
              field("Service / tier name", "name", a.name, "text", "required") +
              area(
                "Service description and inclusions",
                "description",
                a.description,
              ) +
              select(
                "Billing unit",
                "unit",
                ["visit", "night", "hour", "chaperone-hour"].map((x) => [x, x]),
                a.unit,
              ) +
              field(
                "Effective from",
                "effective",
                a.effective,
                "date",
                "required",
              ) +
              field(
                "Client reply contact",
                "contact",
                a.contact,
                "text",
                "required",
              ) +
              num("Base rate per unit ($)", "base", true) +
              num("Visit duration / minimum hourly minutes", "minutes") +
              num("Minimum charge ($)", "minimum", true) +
              num("Included pets", "includedPets") +
              num("Additional pet fee per service unit ($)", "extraPet", true) +
              num("Included travel miles", "includedMiles") +
              num("Per extra mile ($)", "mileRate", true) +
              num("Long stay starts after nights", "longAfter") +
              num("Fee per extra night ($)", "longFee", true) +
              field("Optional add-on name", "addonName", a.addonName) +
              num("Add-on unit price ($)", "addon", true),
          )) +
      '<div class="actions"><button>Save pricing version</button>' +
      button("Clear form", "prices", true) +
      "</div></form>",
  );
}
function joined(profile) {
  if (!profile) return "No sign-up recorded";
  return profile.signedUpAt
    ? new Date(profile.signedUpAt).toLocaleString()
    : "Date unavailable for this older account";
}
function myAccount() {
  const me = state.user;
  nav("My account");
  view(
    hero("Team workspace", "My account") +
      '<section class="card"><h2>' +
      esc(me.profile?.name || me.email) +
      "</h2><p>" +
      esc(me.email) +
      "</p><p>" +
      esc(me.role) +
      "</p><p>Signed up: " +
      esc(joined(me.profile)) +
      "</p><p>" +
      (admin()
        ? "You can manage pricing, team access and quotes."
        : sender()
          ? "You can prepare and issue quotes and record client responses."
          : "You can prepare drafts and view the shared quote history.") +
      "</p>" +
      button("Open quotes", "home") +
      "</section>",
  );
}
function team(member = {}) {
  nav("Team");
  view(
    hero("Administration", "Team access") +
      '<section class="card"><h2>Authorized team</h2>' +
      '<div class="tablewrap"><table><thead><tr><th>Employee</th><th>Work email</th><th>Access</th><th>Signed up</th></tr></thead><tbody>' +
      state.team
        .map(
          (m) =>
            "<tr><td>" +
            esc(m.profile?.name || "—") +
            "</td><td>" +
            button(m.email, "member", true, m.email) +
            "</td><td>" +
            esc(m.role) +
            "</td><td>" +
            esc(joined(m.profile)) +
            "</td></tr>",
        )
        .join("") +
      "</tbody></table></div>" +
      '</section><form id="team" class="stack">' +
      block(
        "Grant or update access",
        field("Team email", "email", member.email, "email", "required") +
          select(
            "Role",
            "role",
            ["Team Member", "Administrator", "Disabled"].map((x) => [x, x]),
            member.role,
          ) +
          '<label><input type="checkbox" name="canSend" ' +
          (member.canSend ? "checked" : "") +
          "> May issue, send and record client responses</label>",
      ) +
      "<p>After granting access, ask the team member to sign up with this email.</p><button>Save access</button></form>",
  );
}
function openQuote(q) {
  q.status === "Draft" ? editor(q) : detail(q);
}
async function history() {
  historical = await api("history", { id: current.id });
  view(
    hero(current.id, "Quote history") +
      '<section class="card">' +
      historical
        .map(
          (h, i) =>
            "<p>" +
            button(
              h.event + " · v" + h.snapshot.revision,
              "snapshot",
              true,
              i,
            ) +
            " " +
            esc(h.actor) +
            " · " +
            esc(new Date(h.at).toLocaleString()) +
            "</p>",
        )
        .reverse()
        .join("") +
      button("Back to quote", "open", true, current.id) +
      "</section>",
  );
}
async function action(a, v) {
  if (a === "mode") {
    account = $("[name=email]").value;
    mode = v;
    auth();
    return;
  }
  if (a === "resend") {
    await api("resend", formData());
    message("Verification code requested.");
    return;
  }
  if (a === "logout") {
    await api("logout");
    state = null;
    current = null;
    historical = null;
    mode = "login";
    auth();
    return;
  }
  if (a === "home") {
    await load();
    home();
    return;
  }
  if (a === "stats") {
    const result = await api("stats");
    message("Export saved: " + result.key);
    return;
  }
  if (a === "addvisit") {
    $("#visitRows").insertAdjacentHTML("beforeend", visitRow());
    $("#calc").innerHTML = "";
    return;
  }
  if (a === "new") {
    editor(null);
    return;
  }
  if (a === "open") {
    openQuote(state.quotes.find((q) => q.id === v));
    return;
  }
  if (a === "prices") {
    prices();
    return;
  }
  if (a === "editprice") {
    prices(state.prices.find((p) => p.id === v));
    return;
  }
  if (a === "account") {
    myAccount();
    return;
  }
  if (a === "team") {
    team();
    return;
  }
  if (a === "member") {
    team(state.team.find((m) => m.email === v) || state.user);
    return;
  }
  if (a === "calculate" || a === "issue") {
    const input = quoteData();
    const result = await api("preview", input);
    $("#calc").innerHTML = '<div class="card">' + table(result) + "</div>";
    if (a === "calculate") {
      return;
    }
    if (
      !confirm(
        "Issue this estimate for " +
          money(result.total) +
          "? Its pricing and issue date will be fixed.",
      )
    )
      return;
    const saved = await api("save", input);
    current = saved;
    const p = state.plans.find((x) => x.planId === input.fields.planId);
    const q = await api("issue", {
      id: saved.id,
      version: saved.version,
      priceVersion: p?.id,
    });
    await load();
    detail(q);
    return;
  }
  if (a === "print") {
    window.print();
    return;
  }
  if (a === "copy") {
    await navigator.clipboard.writeText(estimateText(current));
    message("Estimate copied for email.");
    return;
  }
  if (a === "history") {
    await history();
    return;
  }
  if (a === "snapshot") {
    detail(historical[Number(v)].snapshot, true);
    return;
  }
  if (["sent", "accept", "decline", "revise"].includes(a)) {
    const labels = {
      sent: "Confirm you have delivered this estimate to the client?",
      accept: "Record the client’s request for a Meet & Greet?",
      decline: "Record that the client declined?",
      revise: "Create a new draft and supersede the current version?",
    };
    if (!confirm(labels[a])) return;
    const q = await api(a, { id: current.id, version: current.version });
    await load();
    openQuote(q);
  }
}
function estimateText(q) {
  return [
    "Pawsitive Impact Pet Care",
    q.id + " · v" + q.revision,
    q.fields.client,
    q.fields.start + " through " + q.fields.end,
    "Issued " + q.issued + " · Valid through " + q.expires,
    q.pricing.name,
    q.pricing.description,
    careSummary(q),
    ...q.estimate.items.map(
      (i) =>
        i.label +
        " · " +
        i.units +
        " × " +
        money(i.rate) +
        " = " +
        money(i.amount),
    ),
    "Subtotal " + money(q.estimate.subtotal),
    "Estimated total " + money(q.estimate.total),
    q.fields.notes,
    "Reply to " + q.pricing.contact + " to request a Meet & Greet or decline.",
    disclaimer,
  ]
    .filter(Boolean)
    .join("\n");
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-action]");
  if (!b) return;
  if (b.dataset.action === "removevisit") {
    b.parentElement.remove();
    $("#calc").innerHTML = "";
    return;
  }
  b.disabled = true;
  try {
    await action(b.dataset.action, b.dataset.val);
  } catch (err) {
    message(err.message, true);
  } finally {
    b.disabled = false;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.name === "search") $("#rows").innerHTML = rows(e.target.value);
  if (e.target.closest("#quote")) {
    if (e.target.name === "planId") planInfo(quoteData().fields);
    $("#calc").innerHTML = "";
  }
});
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target,
    d = formData(),
    submit = f.querySelector("button[type=submit],button:not([type])");
  submit.disabled = true;
  try {
    if (f.id === "auth") {
      account = d.email;
      const result = await api(mode, d);
      if (result.ok) {
        await load();
        home();
      } else {
        mode = result.confirm ? "confirm" : "login";
        auth();
        message(
          result.confirm
            ? "Check your email for the verification code."
            : "Your account is ready. Sign in to continue.",
        );
      }
    }
    if (f.id === "quote") {
      const q = await api("save", quoteData());
      await load();
      editor(q);
      message("Draft saved.");
    }
    if (f.id === "price") {
      for (const k of [
        "base",
        "minimum",
        "extraPet",
        "mileRate",
        "longFee",
        "addon",
      ])
        d[k] = cents(d[k]);
      for (const k of ["minutes", "includedPets", "includedMiles", "longAfter"])
        d[k] = Number(d[k] || 0);
      if (editPrice?.sheet)
        d.rates = Object.fromEntries(
          Object.keys(editPrice.rates).map((k) => [k, cents(d["rate_" + k])]),
        );
      await api("price", { ...d, planId: editPrice?.planId });
      await load();
      prices();
      message("Pricing version saved.");
    }
    if (f.id === "team") {
      await api("team", {
        ...d,
        canSend: d.canSend === "on",
        version:
          state.team.find((m) => m.email === d.email.trim().toLowerCase())
            ?.version || 0,
      });
      await load();
      team();
      message("Team access updated.");
    }
  } catch (err) {
    message(err.message, true);
  } finally {
    submit.disabled = false;
  }
});
try {
  await load();
  home();
} catch (err) {
  auth();
  if (!err.message.includes("Sign in")) message(err.message, true);
}
