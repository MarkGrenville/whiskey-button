import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.0/firebase-app.js";
import {
  getDatabase,
  ref,
  set,
  onValue,
} from "https://www.gstatic.com/firebasejs/11.6.0/firebase-database.js";

const firebaseConfig = {
  projectId: "whiskey-dashboard",
  databaseURL: "https://whiskey-dashboard-default-rtdb.firebaseio.com",
};

const app = initializeApp(firebaseConfig);
const db = getDatabase(app);
const resetRef = ref(db, "reset");
const configRef = ref(db, "config");

const statusEl = document.getElementById("status");
const confirmEl = document.getElementById("confirm");
const resetBtn = document.getElementById("resetBtn");
const durationInput = document.getElementById("durationInput");
const maxPoursInput = document.getElementById("maxPoursInput");
const updateBtn = document.getElementById("updateBtn");
const settingsConfirmEl = document.getElementById("settingsConfirm");

const MIN_DURATION = 0.1;
const MAX_DURATION = 30;
const MIN_POURS = 1;
const MAX_POURS = 100;

let pendingSince = null;
let settingsPendingSince = null;
let durationEdited = false;
let maxPoursEdited = false;

onValue(resetRef, (snapshot) => {
  const data = snapshot.val();
  if (!data || !data.resetAt) {
    statusEl.textContent = "No resets yet.";
    confirmEl.textContent = "";
    resetBtn.disabled = false;
    return;
  }

  const sent = new Date(data.resetAt);
  statusEl.innerHTML = `Last reset: <time>${sent.toLocaleString()}</time>`;

  if (data.confirmedAt) {
    const ack = new Date(data.confirmedAt);
    confirmEl.textContent = `Confirmed by Pi at ${ack.toLocaleTimeString()}.`;
    confirmEl.style.color = "#6ab04c";
    pendingSince = null;
  } else if (pendingSince) {
    const wait = Math.round((Date.now() - pendingSince) / 1000);
    confirmEl.textContent = `Waiting for Pi to confirm… (${wait}s)`;
    confirmEl.style.color = "#f0a500";
  }

  resetBtn.disabled = false;
});

resetBtn.addEventListener("click", async () => {
  resetBtn.disabled = true;
  confirmEl.textContent = "";

  try {
    pendingSince = Date.now();
    await set(resetRef, { resetAt: Date.now() });
    confirmEl.textContent = "Reset sent — waiting for Pi to confirm…";
    confirmEl.style.color = "#f0a500";
  } catch (err) {
    confirmEl.textContent = "Error: " + err.message;
    confirmEl.style.color = "#e74c3c";
    pendingSince = null;
  }

  resetBtn.disabled = false;
});

// Enable the settings controls right away so they're usable even before (or
// without) a successful read of the config node.
durationInput.disabled = false;
maxPoursInput.disabled = false;
updateBtn.disabled = false;

// Don't overwrite what the user is typing when live updates arrive.
durationInput.addEventListener("input", () => {
  durationEdited = true;
});
maxPoursInput.addEventListener("input", () => {
  maxPoursEdited = true;
});

onValue(configRef, (snapshot) => {
  const data = snapshot.val();
  durationInput.disabled = false;
  maxPoursInput.disabled = false;
  updateBtn.disabled = false;

  if (!data) {
    settingsConfirmEl.textContent = "No settings sent yet.";
    settingsConfirmEl.style.color = "#9e9e9e";
    return;
  }

  const activeDuration =
    data.activeDuration != null ? data.activeDuration : data.pourDuration;
  const activeMaxPours =
    data.activeMaxPours != null ? data.activeMaxPours : data.maxPours;

  // Reflect the live values unless the user is mid-edit.
  if (activeDuration != null && !durationEdited && document.activeElement !== durationInput) {
    durationInput.value = activeDuration;
  }
  if (activeMaxPours != null && !maxPoursEdited && document.activeElement !== maxPoursInput) {
    maxPoursInput.value = activeMaxPours;
  }

  const summary = describeSettings(activeDuration, activeMaxPours);

  if (data.confirmedAt && data.updatedAt && data.confirmedAt >= data.updatedAt) {
    const ack = new Date(data.confirmedAt);
    settingsConfirmEl.textContent =
      `Active: ${summary} (confirmed by Pi at ${ack.toLocaleTimeString()}).`;
    settingsConfirmEl.style.color = "#6ab04c";
    settingsPendingSince = null;
  } else if (settingsPendingSince) {
    const wait = Math.round((Date.now() - settingsPendingSince) / 1000);
    settingsConfirmEl.textContent = `Waiting for Pi to apply… (${wait}s)`;
    settingsConfirmEl.style.color = "#f0a500";
  } else {
    settingsConfirmEl.textContent = `Current: ${summary}.`;
    settingsConfirmEl.style.color = "#9e9e9e";
  }
}, (err) => {
  // Read denied/failed — keep controls usable and explain why.
  durationInput.disabled = false;
  maxPoursInput.disabled = false;
  updateBtn.disabled = false;
  settingsConfirmEl.textContent =
    "Can't read settings (deploy database rules?): " + err.message;
  settingsConfirmEl.style.color = "#e74c3c";
});

updateBtn.addEventListener("click", async () => {
  const seconds = parseFloat(durationInput.value);
  const pours = parseInt(maxPoursInput.value, 10);

  if (!Number.isFinite(seconds) || seconds < MIN_DURATION || seconds > MAX_DURATION) {
    settingsConfirmEl.textContent =
      `Pour duration must be between ${MIN_DURATION} and ${MAX_DURATION} seconds.`;
    settingsConfirmEl.style.color = "#e74c3c";
    return;
  }

  if (!Number.isInteger(pours) || pours < MIN_POURS || pours > MAX_POURS) {
    settingsConfirmEl.textContent =
      `Pours per day must be a whole number between ${MIN_POURS} and ${MAX_POURS}.`;
    settingsConfirmEl.style.color = "#e74c3c";
    return;
  }

  updateBtn.disabled = true;
  durationEdited = false;
  maxPoursEdited = false;

  try {
    settingsPendingSince = Date.now();
    await set(configRef, {
      pourDuration: seconds,
      maxPours: pours,
      updatedAt: Date.now(),
    });
    settingsConfirmEl.textContent = "Sent — waiting for Pi to apply…";
    settingsConfirmEl.style.color = "#f0a500";
  } catch (err) {
    settingsConfirmEl.textContent = "Error: " + err.message;
    settingsConfirmEl.style.color = "#e74c3c";
    settingsPendingSince = null;
  }

  updateBtn.disabled = false;
});

function describeSettings(duration, pours) {
  const parts = [];
  if (duration != null) parts.push(formatSeconds(duration));
  if (pours != null) parts.push(`${pours} pour${pours === 1 ? "" : "s"}/day`);
  return parts.length ? parts.join(", ") : "—";
}

function formatSeconds(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return `${value}s`;
  return `${parseFloat(n.toFixed(2))}s`;
}
