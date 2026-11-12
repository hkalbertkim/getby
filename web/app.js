"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const cash = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: n % 100 ? 2 : 0,
  }).format(n / 100);
const pair = (a, b) =>
  '<div class="pair"><span>' + esc(a) + "</span><b>" + esc(b) + "</b></div>";
const btn = (label, action, key = "", primary = false) =>
  '<button class="' +
  (primary ? "primary" : "minor") +
  '" data-act="' +
  action +
  '" data-key="' +
  esc(key) +
  '">' +
  esc(label) +
  "</button>";
const names = {
  voice: "Record Korean phrases",
  review: "Compare AI answers",
  receipt: "Check receipt totals",
  photo: "License a photo",
  royalty: "October photo royalty",
};
const labels = {
  submitted: "Awaiting buyer review",
  listed: "Listed · awaiting sale",
  revise: "Edit requested",
  approved: "Approved · awaiting payout",
  pending: "Payout pending",
  received: "Payment received",
  failed: "Payout needs attention",
};
const order = ["voice", "review", "receipt", "photo"];
const icons = { voice: "♪", review: "◎", receipt: "▤", photo: "▧" };
let state,
  token,
  view = "work",
  selected = "",
  draft = null,
  scanStatus = "",
  scouting = false,
  toastTimer,
  audioBlob,
  photoBlob,
  previewUrl,
  recorder,
  activeStream,
  scanPreview;
let publicJobs = null;
let profile = { language: "ko", minutes: 10, photos: true };
try {
  Object.assign(
    profile,
    JSON.parse(localStorage.getItem("getby-profile") || "{}"),
  );
} catch {}
const errorMsg = (e) => e.message || String(e);
function notice(message) {
  $("#toast").textContent = message;
  $("#toast").className = "show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").className = ""), 5500);
}
async function api(route, body) {
  const r = await fetch(
    "/api/" + route,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-GetBy-Session": token,
          },
          body: JSON.stringify(body),
        },
  );
  const result = await r.json();
  if (!r.ok) throw Error(result.error || "Request failed.");
  return result;
}
async function refresh() {
  state = await api("state");
  token = state.token;
  render();
}
function releaseMedia() {
  if (recorder?.state === "recording") {
    recorder.onstop = null;
    recorder.stop();
  }
  activeStream?.getTracks().forEach((t) => t.stop());
  activeStream = null;
  recorder = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = "";
  audioBlob = null;
  photoBlob = null;
}
function go(next) {
  releaseMedia();
  selected = "";
  view = next;
  render();
}
function jobs() {
  return state.matches
    .flatMap((x) => x.jobs)
    .sort(
      (a, b) =>
        (order.includes(a.id) ? order.indexOf(a.id) : 9) -
        (order.includes(b.id) ? order.indexOf(b.id) : 9),
    );
}
function render() {
  const covered = state.total
    ? Math.max(0, Math.min(1, (state.total - state.gap) / state.total))
    : 0;
  $(".ring").style.setProperty("--pct", Math.round(covered * 100) + "%");
  const paid = state.total > 0 && state.paid === state.total;
  $("#ring-label").textContent = paid
    ? "Left after bills"
    : state.total
      ? "Still to earn"
      : "Available";
  $("#ring-value").textContent = cash(
    state.total && !paid ? state.gap : state.balance,
  );
  $("#ring-sub").textContent = paid
    ? "Both sides reconciled"
    : state.total
      ? Math.round(covered * 100) + "% of bills covered"
      : "Opening demo allocation";
  $("#numbers").innerHTML =
    pair("Bills this cycle", cash(state.total)) +
    pair("Available now", cash(state.balance)) +
    pair("Work income received", cash(state.earned));
  $("#mode").textContent =
    state.mode === "sandbox" ? "PayPal Sandbox" : "Practice";
  $("#mode-detail").textContent =
    state.mode === "sandbox"
      ? "Sandbox test accounts · $50 opening demo allocation"
      : "Practice ledger · sample funds and local receipts";
  $("#location").textContent = {
    work: "Work",
    bills: "Bills",
    activity: "Activity",
    buyer: "Test buyer desk",
  }[view];
  document.querySelectorAll("nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    b.setAttribute("aria-current", b.dataset.view === view ? "page" : "false");
  });
  $("#panel").innerHTML = {
    work: workScreen,
    bills: billsScreen,
    activity: activityScreen,
    buyer: buyerScreen,
  }[view]();
}
function heading(ey, title, sub) {
  return (
    '<div class="ey">' +
    esc(ey) +
    "</div><h1>" +
    esc(title) +
    '</h1><p class="sub">' +
    esc(sub) +
    "</p>"
  );
}
function workScreen() {
  const intro = heading(
    "Opportunity scouts",
    "Work toward your bills",
    state.total
      ? state.gap
        ? "Find paid work for the " + cash(state.gap) + " still due this cycle."
        : "Your registered bills are covered. You can keep earning."
      : "Start with a bill to see how much you need to earn.",
  );
  if (!state.bills.length)
    return (
      intro +
      '<div class="upload"><h2>Add your first bill</h2><p class="sub">Photograph a statement or try one of the sample bills.</p>' +
      btn("Add a bill", "toBills", "", true) +
      "</div>"
    );
  const options =
    "<details " +
    (!state.matches.length && !scouting ? "open" : "") +
    '><summary>Work preferences</summary><div class="formrow"><label class="field">Working language<select id="language"><option value="ko" ' +
    (profile.language === "ko" ? "selected" : "") +
    '>Korean</option><option value="en" ' +
    (profile.language === "en" ? "selected" : "") +
    '>English</option></select></label><label class="field">Time per quest<select id="minutes">' +
    [5, 10, 20, 30, 45, 60]
      .map(
        (n) =>
          '<option value="' +
          n +
          '" ' +
          (n === profile.minutes ? "selected" : "") +
          ">" +
          n +
          " minutes</option>",
      )
      .join("") +
    '</select></label></div><label class="check"><input id="photos" type="checkbox" ' +
    (profile.photos ? "checked" : "") +
    ">Include opportunities for photos I choose</label></details>";
  const matched = jobs();
  const plan = state.plan;
  const suggested =
    plan && !scouting
      ? '<div class="plan"><small>Suggested work plan</small><b>' +
        esc(cash(plan.reward)) +
        " in potential rewards · " +
        esc(plan.minutes) +
        " min of work</b><span>" +
        esc(plan.ids.map((id) => names[id]).join(" + ")) +
        "</span><span>" +
        esc(
          plan.remaining
            ? cash(plan.remaining) + " would still be needed."
            : "Estimated paydays cover your registered bills.",
        ) +
        "</span></div>"
      : "";
  return (
    intro +
    suggested +
    options +
    '<div class="btns">' +
    (scouting
      ? '<span class="loading" role="status">Scouts are reading the briefs…</span>'
      : btn(
          state.matches.length ? "Refresh matches" : "Find paid work",
          "scout",
          "",
          true,
        )) +
    "</div>" +
    (state.matches.length
      ? '<div class="lanes">' +
        state.matches
          .map(
            (m) =>
              '<span class="lane" title="' +
              esc(m.engine) +
              '">' +
              esc(m.agent) +
              " · " +
              m.jobs.length +
              "</span>",
          )
          .join("") +
        "</div>"
      : "") +
    matched
      .map(
        (j) =>
          '<article class="job"><button class="jobhead" data-act="open" data-key="' +
          esc(j.id) +
          '" aria-expanded="' +
          (selected === j.id) +
          '"><span class="pic">' +
          (icons[j.id] || "◇") +
          "</span><span><b>" +
          esc(j.title) +
          "</b><small>" +
          esc(
            labels[state.work[j.id]?.state] || j.minutes + " min · " + j.agent,
          ) +
          '</small></span><strong class="reward">' +
          (j.reward ? cash(j.reward) : "On sale") +
          "<small>" +
          esc(j.reward ? "per task" : "photo license") +
          "</small></strong></button>" +
          (selected === j.id ? jobDetail(j) : "") +
          "</article>",
      )
      .join("") +
    (state.matches.length
      ? '<p class="source">Source · Get By test buyer catalog. Open a brief for payday estimates and matching details.</p><details><summary>Explore external work sources</summary><p class="hint">Check current availability, terms and pay with each provider.</p><div class="btns"><a href="https://www.clickworker.com/clickworker/" target="_blank" rel="noreferrer">Clickworker</a> <a href="https://www.prolific.com/participants" target="_blank" rel="noreferrer">Prolific studies</a> <a href="https://contributor.stock.adobe.com/" target="_blank" rel="noreferrer">Adobe Stock</a></div>' +
        btn("Search live documentation bounties", "public") +
        '<div id="publicList">' +
        publicResults() +
        "</div></details>"
      : "")
  );
}
function publicResults() {
  if (!publicJobs) return "";
  if (!publicJobs.length) return "<p>No open briefs found for this search.</p>";
  return (
    '<p class="hint">Open GitHub issues tagged as bounties. Reward, eligibility and payday require issuer confirmation.</p>' +
    publicJobs
      .map(
        (j) =>
          '<p><a target="_blank" rel="noreferrer" href="' +
          esc(j.url) +
          '">' +
          esc(j.title) +
          "</a><small> · " +
          esc(j.source) +
          "</small></p>",
      )
      .join("")
  );
}
function jobDetail(j) {
  const w = state.work[j.id],
    r = state.matches.find((m) => m.agent === j.agent);
  const summary =
    "<p>" +
    esc(j.brief) +
    '</p><p class="hint"><b>' +
    esc(r.engine) +
    "</b> · " +
    esc(j.reason) +
    '</p><p class="hint">Expected payment · ' +
    esc(j.timing || "After buyer review") +
    "</p><ol>" +
    j.steps.map((s) => "<li>" + esc(s) + "</li>").join("") +
    "</ol>";
  if (w && w.state !== "revise")
    return (
      '<div class="detail">' +
      summary +
      '<strong class="status">' +
      esc(labels[w.state]) +
      "</strong></div>"
    );
  const common = '<p class="status">' + esc(w?.note || "") + "</p>";
  let form = "";
  if (j.id === "voice")
    form =
      '<div lang="ko">' +
      state.prompts.map((p) => "<p>" + esc(p) + "</p>").join("") +
      '</div><div class="btns">' +
      btn("Record", "record") +
      btn("Use sample audio", "sampleAudio") +
      '</div><input type="file" id="voicefile" accept="audio/*" aria-label="Upload recording"><div id="audioPreview"></div><label class="check"><input type="checkbox" id="consent">I permit local review of this recording.</label>';
  if (j.id === "review")
    form =
      '<p><b>Question</b> · When is my bill due?</p><p>A · “Your payment must arrive by November 20.”</p><p>B · “Soon, based on your cycle.”</p><label class="field">Preferred answer<select id="choice"><option>A</option><option>B</option></select></label><label class="field">Reason<textarea id="reason" maxlength="500"></textarea></label>';
  if (j.id === "receipt")
    form =
      '<div class="sample"><b>Market receipt</b>' +
      pair("Notebook", "$8.00") +
      pair("Pens", "$4.00") +
      pair("Tax", "$1.20") +
      '</div><label class="field">Correct total (USD)<input id="amount" type="number" min=".01" step=".01"></label>';
  if (j.id === "photo")
    form =
      '<input id="photofile" type="file" accept="image/*" aria-label="Choose photo"><div class="btns">' +
      btn("Use sample still life", "samplePhoto") +
      '</div><div id="photoPreview"></div><label class="field">Photo caption<input id="caption" maxlength="300"></label><label class="check"><input type="checkbox" id="consent">I have permission to list this photo.</label>';
  return (
    '<div class="detail">' +
    summary +
    common +
    form +
    (j.kind === "external"
      ? '<span class="status">Preview brief · enrollment opens next cycle</span>'
      : btn(
          j.id === "photo" ? "List photo" : "Submit work",
          "submit",
          j.id,
          true,
        )) +
    "</div>"
  );
}
function billsScreen() {
  const cards = state.bills
    .map(
      (b) =>
        '<article class="bill"><div class="row"><b>' +
        esc(b.issuer) +
        "</b><strong>" +
        cash(b.cents) +
        "</strong></div><small>Due " +
        esc(b.due) +
        "</small>" +
        (b.state === "paid"
          ? '<p class="good">Paid · ' +
            esc(state.mode) +
            '</p><div class="ledgerref">' +
            esc(b.receipt) +
            "</div>"
          : '<div class="btns">' +
            btn(
              b.state === "approval"
                ? "Continue PayPal approval"
                : "Pay this bill",
              "pay",
              b.role,
            ) +
            "</div>") +
        "</article>",
    )
    .join("");
  const form = draft
    ? '<form id="billform"><h2>Confirm bill details</h2>' +
      (scanPreview
        ? '<img class="sampleimg" alt="Uploaded statement" src="' +
          esc(scanPreview) +
          '">'
        : "") +
      '<label class="field">Biller<input name="issuer" required value="' +
      esc(draft.issuer) +
      '"></label><div class="formrow"><label class="field">Amount (USD)<input name="amount" type="number" step=".01" min=".01" required value="' +
      (draft.cents ? draft.cents / 100 : "") +
      '"></label><label class="field">Due date<input name="due" type="date" required value="' +
      esc(draft.due) +
      '"></label></div><label class="field">Bill type<select name="role"><option value="electricity">Electricity</option><option value="mobile" ' +
      (draft.role === "mobile" ? "selected" : "") +
      '>Mobile</option></select></label><div class="btns"><button class="primary" type="submit">Save bill</button><button type="button" data-act="cancelScan" class="minor">Cancel</button></div></form>'
    : '<div class="upload"><b>Scan a statement</b><input id="billfile" type="file" accept="image/*" aria-label="Upload bill photo"><div class="btns">' +
      btn("Electricity sample", "scan", "electricity") +
      btn("Mobile sample", "scan", "mobile") +
      btn("Enter manually", "manual") +
      "</div><small>" +
      esc(scanStatus || "Review the amount and due date before saving.") +
      "</small></div>";
  const autopay = cards
    ? '<label class="check"><input id="autopay" type="checkbox" ' +
      (state.auto_pay ? "checked" : "") +
      ">When all bills are covered, " +
      (state.mode === "practice"
        ? "pay the registered bills from this practice balance."
        : "prepare PayPal checkouts for the registered test billers. I approve each payment in PayPal.") +
      "</label>"
    : "";
  return (
    heading(
      "Billing cycle",
      "Your bills",
      "Upload a statement to calculate the work income you still need.",
    ) +
    cards +
    autopay +
    form +
    (cards
      ? '<div class="btns">' +
        btn("Find work for these bills", "toWork", "", true) +
        "</div>"
      : "")
  );
}
function buyerScreen() {
  return (
    heading(
      "Test buyer",
      "Review desk",
      "Play back the work, approve it, then release the reward.",
    ) +
    Object.values(state.work)
      .sort((a, b) => (a.id === "royalty") - (b.id === "royalty"))
      .map((w) => {
        const ev = JSON.parse(w.evidence || "{}");
        const evidence =
          w.id === "voice"
            ? '<audio controls src="/api/media/voice"></audio>'
            : w.id === "photo"
              ? '<img class="sampleimg" src="/api/media/photo" alt="Submitted photo"><p>' +
                esc(ev.caption) +
                "</p>"
              : w.id === "royalty"
                ? "<p>" + esc(ev.caption) + "</p>"
                : w.id === "review"
                  ? "<p>" + esc(ev.choice) + " · " + esc(ev.reason) + "</p>"
                  : "<p>Recorded total · " + cash(ev.total_cents) + "</p>";
        let controls = "";
        if (["submitted", "listed"].includes(w.state))
          controls =
            btn(
              w.state === "listed" ? "Buy license" : "Approve work",
              "approve",
              w.id,
              true,
            ) +
            (w.state === "submitted"
              ? btn("Request edit", "revise", w.id)
              : "");
        if (["approved", "pending"].includes(w.state))
          controls = btn(
            w.state === "pending" ? "Check payout" : "Release reward",
            "settle",
            w.id,
            true,
          );
        return (
          '<article class="reviewitem"><b>' +
          esc(names[w.id]) +
          "</b><small>" +
          esc(labels[w.state]) +
          "</small>" +
          evidence +
          '<div class="btns">' +
          controls +
          "</div><small>" +
          esc(w.note || "") +
          "</small></article>"
        );
      })
      .join("")
  );
}
function activityScreen() {
  const items = [...state.ledger]
    .reverse()
    .map(
      (e) =>
        '<div class="activity"><div class="row"><b>' +
        esc(e.label) +
        '</b><strong class="' +
        (e.cents > 0 ? "good" : "") +
        '">' +
        (e.cents > 0 ? "+" : "") +
        cash(e.cents) +
        '</strong></div><small class="ledgerref">' +
        esc(e.ref) +
        "</small></div>",
    )
    .join("");
  const waiting = Object.values(state.work)
    .filter((w) => w.state !== "received")
    .map(
      (w) =>
        '<div class="pair"><span>' +
        esc(names[w.id]) +
        "</span><small>" +
        esc(labels[w.state]) +
        "</small></div>",
    )
    .join("");
  const surplus =
    state.bills.length && state.paid === state.total && state.balance > 0;
  return (
    heading(
      "Account activity",
      "Follow your earnings",
      "Each confirmed receipt changes your available balance once.",
    ) +
    items +
    (waiting ? "<h2>Awaiting income</h2>" + waiting : "") +
    (surplus
      ? '<details class="detail" id="usdc"><summary>Explore 30-day USDC options · ' +
        cash(state.balance) +
        '</summary><p class="hint">Illustrative variable rates. Estimates assume 1 USD = 1 USDC and exclude fees. Principal and rates can change.</p>' +
        [
          ["USDC lending pool", 0.035],
          ["USDC vault", 0.05],
        ]
          .map(([n, rate]) =>
            pair(
              n + " · " + (rate * 100).toFixed(1) + "% APR",
              "≈ " +
                (((state.balance / 100) * rate * 30) / 365).toFixed(3) +
                " USDC",
            ),
          )
          .join("") +
        "</details>"
      : "")
  );
}
async function encoded(blob) {
  if (!blob || blob.size > 5000000)
    throw Error("Choose a file smaller than 5 MB.");
  return new Promise((resolve, reject) => {
    const f = new FileReader();
    f.onload = () => resolve(f.result.split(",")[1]);
    f.onerror = () => reject(Error("File could not be read."));
    f.readAsDataURL(blob);
  });
}
async function sample(name) {
  const r = await fetch("/samples/" + name);
  if (!r.ok) throw Error("Sample missing.");
  return r.blob();
}
async function scan(blob) {
  scanStatus = "Reading statement…";
  draft = null;
  render();
  if (scanPreview) URL.revokeObjectURL(scanPreview);
  scanPreview = URL.createObjectURL(blob);
  try {
    draft = await api("scan", { data: await encoded(blob) });
  } catch (e) {
    draft = {};
    notice(errorMsg(e));
  } finally {
    scanStatus = "";
    render();
  }
}
function mediaPreview(blob, audio) {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(blob);
  if (audio) {
    audioBlob = blob;
    $("#audioPreview").innerHTML = "<audio controls></audio>";
    $("#audioPreview audio").src = previewUrl;
  } else {
    photoBlob = blob;
    $("#photoPreview").innerHTML = '<img width="140" alt="Photo selected">';
    $("#photoPreview img").src = previewUrl;
  }
}
async function record(button) {
  if (recorder?.state === "recording") {
    recorder.stop();
    button.textContent = "Record again";
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
    throw Error(
      "This browser cannot record here. Upload audio or use the sample.",
    );
  try {
    activeStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    throw Error(
      "Microphone access is unavailable. Upload audio or use the sample.",
    );
  }
  const stream = activeStream;
  recorder = new MediaRecorder(stream);
  const chunks = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  recorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    mediaPreview(new Blob(chunks, { type: recorder.mimeType }), true);
  };
  recorder.start();
  button.textContent = "Stop recording";
}
async function submit(id) {
  let body = { id };
  if (id === "voice" || id === "photo") {
    const blob = id === "voice" ? audioBlob : photoBlob;
    if (!blob) throw Error("Record or choose a sample first.");
    Object.assign(body, {
      data: await encoded(blob),
      mime: blob.type,
      consent: $("#consent").checked,
      caption: $("#caption")?.value,
    });
  } else if (id === "review") {
    Object.assign(body, {
      choice: $("#choice").value,
      reason: $("#reason").value,
    });
  } else body.total_cents = Math.round(Number($("#amount").value) * 100);
  await api("submit", body);
  releaseMedia();
  await refresh();
  notice(
    id === "photo"
      ? "Photo listed. Income depends on a sale."
      : "Work submitted for buyer review.",
  );
}
async function discover() {
  if (scouting) return;
  profile = {
    language: $("#language").value,
    minutes: Number($("#minutes").value),
    photos: $("#photos").checked,
  };
  localStorage.setItem("getby-profile", JSON.stringify(profile));
  scouting = true;
  selected = "";
  releaseMedia();
  render();
  const outcomes = await Promise.allSettled(
    ["Speech", "Evaluation", "Licensing"].map(async (agent) => {
      await api("scout", { agent, ...profile });
      await refresh();
    }),
  );
  scouting = false;
  await refresh();
  const failed = outcomes.find((x) => x.status === "rejected");
  if (failed) throw failed.reason;
}
async function payment(role, redirect = true) {
  const result = await api("pay", { role });
  await refresh();
  if (result.state === "approval" && redirect) {
    location.assign(result.link);
    return;
  }
  notice(
    result.state === "paid"
      ? "Bill paid. Receipt added to activity."
      : result.state === "open"
        ? "The previous order closed. You can start a new payment."
        : "Awaiting buyer approval.",
  );
}
document.addEventListener("click", async (e) => {
  const el = e.target.closest("button");
  if (!el) return;
  if (el.dataset.view) {
    go(el.dataset.view);
    return;
  }
  if (!el.dataset.act) return;
  const { act, key } = el.dataset;
  el.disabled = true;
  try {
    switch (act) {
      case "public":
        el.textContent = "Searching GitHub…";
        try {
          publicJobs = (await api("public-work", { category: "documentation" }))
            .jobs;
          $("#publicList").innerHTML = publicResults();
        } finally {
          el.textContent = "Search live documentation bounties";
        }
        break;
      case "toBills":
        go("bills");
        break;
      case "toWork":
        go("work");
        break;
      case "manual":
        draft = {};
        if (scanPreview) URL.revokeObjectURL(scanPreview);
        scanPreview = null;
        render();
        break;
      case "cancelScan":
        draft = null;
        render();
        break;
      case "scan":
        await scan(await sample(key + ".png"));
        break;
      case "scout":
        await discover();
        break;
      case "open":
        releaseMedia();
        selected = selected === key ? "" : key;
        render();
        break;
      case "record":
        await record(el);
        break;
      case "sampleAudio":
        mediaPreview(await sample("voice.wav"), true);
        break;
      case "samplePhoto":
        mediaPreview(await sample("photo.jpg"), false);
        break;
      case "submit":
        await submit(key);
        break;
      case "approve":
      case "revise":
        await api("review", {
          id: key,
          decision: act === "approve" ? "approve" : "revise",
        });
        await refresh();
        break;
      case "settle":
        await api("settle", { id: key });
        await refresh();
        break;
      case "pay":
        await payment(key);
        break;
    }
  } catch (e) {
    notice(errorMsg(e));
  } finally {
    el.disabled = false;
  }
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "autopay") {
    try {
      await api("preferences", { enabled: e.target.checked });
      await refresh();
      notice("Payment preference saved.");
    } catch (err) {
      await refresh();
      notice(errorMsg(err));
    }
    return;
  }
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    if (e.target.id === "billfile") await scan(file);
    if (e.target.id === "voicefile") mediaPreview(file, true);
    if (e.target.id === "photofile") mediaPreview(file, false);
  } catch (err) {
    notice(errorMsg(err));
  }
});
document.addEventListener("submit", async (e) => {
  if (e.target.id !== "billform") return;
  e.preventDefault();
  const form = e.target;
  const raw = Object.fromEntries(new FormData(form));
  try {
    await api("bills", { ...raw, cents: Math.round(Number(raw.amount) * 100) });
    draft = null;
    await refresh();
    notice("Bill added to this cycle.");
  } catch (err) {
    notice(errorMsg(err));
  }
});
(async () => {
  try {
    await refresh();
    const role = new URLSearchParams(location.search).get("bill");
    if (role) {
      go("bills");
      history.replaceState({}, "", "/");
      await payment(role, false);
    }
  } catch (e) {
    notice(errorMsg(e));
  }
})();

// A background settlement updates the ring while keeping active drafts intact.
setInterval(async () => {
  if (
    !state ||
    scouting ||
    selected ||
    draft ||
    scanStatus ||
    document.hidden ||
    !["work", "bills", "activity", "buyer"].includes(view)
  )
    return;
  if (
    !state.auto_pay &&
    !Object.values(state.work).some((w) => w.state === "pending")
  )
    return;
  try {
    const next = await api("state");
    const changed =
      JSON.stringify(next.ledger) !== JSON.stringify(state.ledger) ||
      JSON.stringify(next.bills) !== JSON.stringify(state.bills) ||
      JSON.stringify(next.work) !== JSON.stringify(state.work);
    if (changed) {
      state = next;
      render();
    }
  } catch {
    /* Manual actions report connectivity errors. */
  }
}, 10000);
