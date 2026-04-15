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

const statusEl = document.getElementById("status");
const confirmEl = document.getElementById("confirm");
const resetBtn = document.getElementById("resetBtn");

let pendingSince = null;

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
