// Mossy: a tiny made-up plant-care app for testing the walkthrough rig.
// Everything lives in memory, so a reload resets it (that's the "demo data reset").
"use strict";

const ROOMS = ["Living room", "Kitchen", "Bedroom", "Office", "Bathroom"];

// daysAgo: days since it was last watered. every: water every N days.
const plants = [
  { id: 1, name: "Boston fern", room: "Living room", every: 3, daysAgo: 3 },
  { id: 2, name: "Basil", room: "Kitchen", every: 2, daysAgo: 3 },
  { id: 3, name: "Snake plant", room: "Bedroom", every: 14, daysAgo: 4 },
  { id: 4, name: "Pothos", room: "Office", every: 7, daysAgo: 6 },
  { id: 5, name: "Rosemary", room: "Kitchen", every: 4, daysAgo: 1 },
  { id: 6, name: "Monstera", room: "Living room", every: 7, daysAgo: 2 },
];
let nextId = 7;
let roomFilter = "All rooms";
let justAdded = null;
const settings = { reminders: true, time: "8:00 AM" };

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function status(p) {
  const left = p.every - p.daysAgo;
  if (left < 0) return { cls: "late", text: `${-left} day${left === -1 ? "" : "s"} late` };
  if (left === 0) return { cls: "due", text: "Water today" };
  return { cls: "ok", text: `In ${left} day${left === 1 ? "" : "s"}` };
}

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove("show"), 1800);
}

function renderPlants() {
  const shown = plants.filter((p) => roomFilter === "All rooms" || p.room === roomFilter);
  const due = plants.filter((p) => p.every - p.daysAgo <= 0).length;
  $("#main").innerHTML = `
    <div class="head">
      <div>
        <h1>Your plants</h1>
        <p class="sub">${due ? `${due} need${due === 1 ? "s" : ""} water today` : "Everything's watered"}</p>
      </div>
      <button class="primary" id="add-open">Add plant</button>
    </div>
    <div class="filters" role="group" aria-label="Room">
      ${["All rooms", ...ROOMS].map((r) => `<button type="button" aria-pressed="${r === roomFilter}" data-room="${esc(r)}">${esc(r)}</button>`).join("")}
    </div>
    <ul class="grid" aria-label="Plants">
      ${shown.map((p) => {
        const s = status(p);
        return `<li class="plant${p.id === justAdded ? " new" : ""}" aria-label="${esc(p.name)}">
          <h3>${esc(p.name)}</h3>
          <div class="meta">${esc(p.room)} · every ${p.every} day${p.every === 1 ? "" : "s"}</div>
          <div class="row">
            <span class="badge ${s.cls}">${s.text}</span>
            <button class="small" data-water="${p.id}">Mark watered</button>
          </div>
        </li>`;
      }).join("")}
    </ul>`;
  justAdded = null;
  $("#add-open").onclick = openAdd;
  for (const b of document.querySelectorAll("[data-room]")) b.onclick = () => { roomFilter = b.dataset.room; renderPlants(); };
  for (const b of document.querySelectorAll("[data-water]")) b.onclick = () => {
    const p = plants.find((x) => x.id === Number(b.dataset.water));
    p.daysAgo = 0;
    renderPlants();
    toast(`Watered ${p.name}`);
  };
}

function renderSettings() {
  $("#main").innerHTML = `
    <div class="head"><div><h1>Settings</h1><p class="sub">How Mossy reminds you</p></div></div>
    <div class="panel">
      <div class="setting">
        <div><strong>Watering reminders</strong><span>A note on the days a plant needs water</span></div>
        <button class="switch" role="switch" aria-label="Watering reminders" aria-checked="${settings.reminders}" id="remind"></button>
      </div>
      <div class="setting">
        <div><strong>Remind me at</strong><span>In your time zone</span></div>
        <select aria-label="Remind me at" id="remind-time">
          ${["7:00 AM", "8:00 AM", "9:00 AM", "6:00 PM"].map((t) => `<option${t === settings.time ? " selected" : ""}>${t}</option>`).join("")}
        </select>
      </div>
    </div>`;
  $("#remind").onclick = (e) => { settings.reminders = !settings.reminders; e.currentTarget.setAttribute("aria-checked", settings.reminders); toast(settings.reminders ? "Reminders on" : "Reminders off"); };
  $("#remind-time").onchange = (e) => { settings.time = e.target.value; toast(`Reminders at ${settings.time}`); };
}

function openAdd() {
  const f = $("#add-form");
  f.reset();
  $("#add-save").disabled = false;
  $("#add-save").textContent = "Save";
  $("#add-dialog").showModal();
  f.plant.focus();
}

$("#add-cancel").onclick = () => $("#add-dialog").close();
$("#add-form").onsubmit = (e) => {
  e.preventDefault();
  const f = e.target;
  const name = f.plant.value.trim();
  if (!name) return;
  const save = $("#add-save");
  save.disabled = true;
  save.textContent = "Saving…";
  // A pretend server round trip, so takes can practise cutting out a wait.
  setTimeout(() => {
    const p = { id: nextId++, name, room: f.room.value, every: Math.max(1, Number(f.every.value) || 7), daysAgo: 0 };
    plants.unshift(p);
    justAdded = p.id;
    roomFilter = "All rooms";
    $("#add-dialog").close();
    renderPlants();
    toast(`Saved ${name}`);
  }, 900);
};

function route() {
  const page = (location.hash.replace(/^#\//, "") || "plants").split("?")[0];
  for (const a of document.querySelectorAll("[data-nav]")) a.classList.toggle("active", a.dataset.nav === page);
  if (page === "settings") renderSettings(); else renderPlants();
}
window.addEventListener("hashchange", route);
route();
