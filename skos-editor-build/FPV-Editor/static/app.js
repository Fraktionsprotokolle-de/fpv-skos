/* app.js — Client-Logik des FPV-Editors (Vanilla JS, kein Framework). */

const App = {
  state: null,        // zuletzt vom Server erhaltener Zustand ({path, sha256, records, findings, ...})
  selectedId: null,   // aktuell ausgewählte ID, oder '__NEW__' bei Neuanlage, oder null
  dirty: false,       // ungespeicherte Änderungen im Formular?
  expandedLetters: new Set(),
  saveFailed: false,  // letzter Speicherversuch schlug fehl (bis zur naechsten Eingabe)
  justSaved: null,    // {id, time, atomic} nach erfolgreichem Speichern
  // Vorgemerkte Aenderungen (noch nicht in der Datei): Schluessel = ID des
  // bestehenden Eintrags bzw. "__NEW__:<n>" fuer neue Eintraege.
  drafts: new Map(),  // key -> {key, originalId|null, data}
  currentKey: null,   // Schluessel des Eintrags, der gerade im Formular steht
  newCounter: 0,
  failedId: null,     // Eintrag, an dem der letzte Sammel-Speichervorgang scheiterte
  // Zwischensicherung (Autorecovery): Meldung der vorgemerkten Eintraege an den
  // Server (fuer das Startfenster) und alle 10 Minuten als Datei auf der Platte.
  syncEnabled: false,   // erst nach der Entscheidung ueber eine vorhandene Zwischensicherung
  persistDueAt: null,   // Zeitpunkt (ms) der naechsten Zwischensicherung auf Platte
  lastPersistTime: null,
  persistError: null,
  // UI-Zustand: Filter im Pruefungspanel und beruehrte Pflichtfelder im Formular.
  findingFilter: "all", // "all" | "error" | "warning"
  touchedFields: new Set(),
};
const AUTOSAVE_INTERVAL_MS = 10 * 60 * 1000;
let syncTimer = null;
let treeSearchTimer = null;
let currentDeleteTargetId = null;
let modalCancelHandler = null;

// ---------------------------------------------------------------------
// Fetch-Hilfsfunktionen
// ---------------------------------------------------------------------

// fetch() wirft bei fehlender Verbindung einen TypeError. Das passiert hier
// praktisch nur, wenn das Programm (kleines Startfenster) beendet wurde.
function connectionError() {
  const err = new Error(
    "Keine Verbindung zum FPV-Editor. Vermutlich wurde das Programm beendet " +
      "(kleines Fenster \u201eFPV-Editor\u201c geschlossen)."
  );
  err.status = 0;
  checkServerAlive();
  return err;
}

async function apiPost(path, body) {
  let resp;
  try {
    resp = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-FPV-Token": window.FPV_TOKEN },
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw connectionError();
  }
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(json.error || `HTTP ${resp.status}`);
    err.status = resp.status;
    err.findings = json.findings;
    err.failedId = json.failed_id || null;
    throw err;
  }
  return json;
}

async function apiGet(path) {
  let resp;
  try {
    resp = await fetch(path);
  } catch {
    throw connectionError();
  }
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(json.error || `HTTP ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  return json;
}

function handleApiError(err, title) {
  let body = err.message || String(err);
  if (err.findings && err.findings.length) {
    body += "\n\n" + err.findings
      .map((f) => `[${f.level === "error" ? "Fehler" : "Hinweis"}] ${f.concept_id ? f.concept_id + ": " : ""}${f.message}`)
      .join("\n");
  }
  if (err.status === 409) {
    body += "\n\nBitte die Datei neu laden (\u201eDatei pr\u00fcfen\u201c) und die \u00c4nderung erneut vornehmen.";
  }
  if (err.status === 507) {
    body += "\n\nEs wurde NICHTS geschrieben, solange keine Sicherung angelegt werden konnte.";
  }
  showModal(title, body, "error");
}

// ---------------------------------------------------------------------
// Status-Banner (Toast) fuer unkritische Rueckmeldungen
// ---------------------------------------------------------------------

let toastTimer = null;
let toastAutoMs = 0;

function showBanner(text, kind, opts) {
  const bar = document.getElementById("toast-bar");
  const inner = document.getElementById("toast-inner");
  const icon = document.getElementById("toast-icon");
  const msg = document.getElementById("toast-text");
  const k = kind || "info";
  const icons = { ok: "\u2713", info: "\u2139", warn: "\u26a0", error: "!" };
  inner.className = "toast-inner kind-" + k;
  icon.textContent = icons[k] || "\u2139";
  msg.textContent = text;
  bar.hidden = false;

  clearTimeout(toastTimer);
  const sticky = !!(opts && opts.sticky);
  toastAutoMs = sticky ? 0 : (opts && opts.durationMs) || (k === "warn" || k === "error" ? 10000 : 6500);
  if (toastAutoMs > 0) {
    toastTimer = setTimeout(hideBanner, toastAutoMs);
  }
}

function hideBanner() {
  clearTimeout(toastTimer);
  toastTimer = null;
  toastAutoMs = 0;
  const bar = document.getElementById("toast-bar");
  if (bar) bar.hidden = true;
}

// ---------------------------------------------------------------------
// Modale Fenster (kritische Meldungen & Sicherheitsabfragen)
// ---------------------------------------------------------------------

function showModal(title, body, kind, opts) {
  modalCancelHandler = null;
  const overlay = document.getElementById("modal-overlay");
  const box = document.getElementById("modal-box");
  // opts.noClose: kein Schliessen-Knopf, Escape wirkt nicht (z. B. solange
  // auf das Dateiauswahlfenster gewartet wird).
  box.className = "modal state-" + (kind || "info") + (opts && opts.noClose ? " no-close" : "");
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").textContent = body;
  document.getElementById("modal-extra").innerHTML = "";
  const closeBtn = document.getElementById("modal-close");
  closeBtn.textContent = kind === "progress" ? "Schlie\u00dfen" : "OK";
  overlay.classList.remove("hidden");
  if (!(opts && opts.noClose)) closeBtn.focus();
}

// Einheitliche Sicherheitsabfrage im App-Design (ersetzt Browser-confirm()).
// Fokus liegt immer auf "Abbrechen", damit versehentliches Enter nie loescht.
function showConfirmModal(title, body, opts) {
  const o = opts || {};
  return new Promise((resolve) => {
    let settled = false;
    const finish = (val) => {
      if (settled) return;
      settled = true;
      modalCancelHandler = null;
      hideModal();
      resolve(val);
    };

    showModal(title, body, o.kind || "warn", { noClose: true });
    modalCancelHandler = () => finish(false);

    const extra = document.getElementById("modal-extra");
    const row = document.createElement("div");
    row.className = "confirm-actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "secondary";
    cancelBtn.textContent = o.cancelLabel || "Abbrechen";
    cancelBtn.addEventListener("click", () => finish(false));

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = o.danger ? "danger" : "";
    okBtn.textContent = o.confirmLabel || "Best\u00e4tigen";
    okBtn.addEventListener("click", () => finish(true));

    row.appendChild(cancelBtn);
    row.appendChild(okBtn);
    extra.appendChild(row);
    cancelBtn.focus();
  });
}

// Unkritische Hinweise & Abbrueche erscheinen oben im Status-Banner statt als
// blockierendes Modal — jede Aktion bleibt dennoch deutlich sichtbar.
function showNothingDone(action, reason) {
  showBanner(`${action}: ${reason}`, "info");
}

function fileBaseName(path) {
  if (!path) return "";
  return String(path).split(/[\\/]/).pop() || path;
}

function requireFile(action) {
  if (App.state && App.state.path) return true;
  showNothingDone(action, "Es ist keine TTL-Datei ge\u00f6ffnet. Bitte zuerst eine Datei \u00f6ffnen.");
  return false;
}

function findingCounts(state) {
  const findings = (state && state.findings) || [];
  return {
    errors: findings.filter((f) => f.level === "error").length,
    warnings: findings.filter((f) => f.level === "warning").length,
  };
}

// Kurzbeschreibung eines geladenen Zustands fuer Dialoge.
function describeState(state) {
  const { errors, warnings } = findingCounts(state);
  const protectedCount = state.records.filter((r) => r.protected).length;
  let text = `${state.path}\n${state.records.length} Konzepte gelesen`;
  if (protectedCount) {
    text += `, davon ${protectedCount} gesch\u00fctzt (nicht \u00fcber das Formular bearbeitbar)`;
  }
  text += ".\n\n";
  text += errors || warnings
    ? `Pr\u00fcfung: ${errors} Fehler, ${warnings} ${warnings === 1 ? "Hinweis" : "Hinweise"} \u2014 Details im Pr\u00fcfungspanel rechts.`
    : "Pr\u00fcfung: keine Fehler und keine Hinweise.";
  return text;
}

function stateKind(state) {
  const { errors, warnings } = findingCounts(state);
  return errors ? "error" : warnings ? "warn" : "ok";
}

function hideModal() {
  modalCancelHandler = null;
  document.getElementById("modal-overlay").classList.add("hidden");
}

function showPromptModal(title, message, onSubmit) {
  const overlay = document.getElementById("modal-overlay");
  const box = document.getElementById("modal-box");
  box.className = "modal state-info";
  document.getElementById("modal-close").textContent = "Abbrechen";
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").textContent = message;
  const extra = document.getElementById("modal-extra");
  extra.innerHTML = "";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "mono";
  input.placeholder = "z. B. C:\\Sicherungen\\FPV";
  input.style.marginTop = "10px";

  const btnRow = document.createElement("div");
  btnRow.style.display = "flex";
  btnRow.style.gap = "8px";
  btnRow.style.marginTop = "10px";

  const okBtn = document.createElement("button");
  okBtn.type = "button";
  okBtn.textContent = "\u00dcbernehmen";
  okBtn.addEventListener("click", () => {
    const v = input.value.trim();
    if (!v) return;
    hideModal();
    onSubmit(v);
  });

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "secondary";
  cancelBtn.textContent = "Abbrechen";
  cancelBtn.addEventListener("click", hideModal);

  btnRow.appendChild(okBtn);
  btnRow.appendChild(cancelBtn);
  extra.appendChild(input);
  extra.appendChild(btnRow);
  overlay.classList.remove("hidden");
  input.focus();
}

// Ausklappbare technische Details im Modal (Pfad, Schreibmethode usw.):
// Laien sehen oben eine klare, knappe Meldung; fuer Rueckfragen oder Support
// bleiben alle technischen Angaben per Klick zugaenglich.
function appendTechDetails(lines) {
  const extra = document.getElementById("modal-extra");
  const details = document.createElement("details");
  details.className = "tech-details";
  const summary = document.createElement("summary");
  summary.textContent = "Technische Details anzeigen";
  const body = document.createElement("div");
  body.className = "tech-details-body";
  body.textContent = (lines || []).filter(Boolean).join("\n");
  details.appendChild(summary);
  details.appendChild(body);
  extra.appendChild(details);
}

function friendlyBackupLocation(loc) {
  const s = String(loc || "");
  if (!s) return "Sicherungsordner";
  if (s.includes("LOCALAPPDATA") || s.includes(".fpv-editor")) return "Automatischer Sicherungsordner";
  if (s.toLowerCase().includes("manuell")) return "Selbst gew\u00e4hlter Ordner";
  return s;
}

function showBackupsModal(backups) {
  const overlay = document.getElementById("modal-overlay");
  const box = document.getElementById("modal-box");
  box.className = "modal state-info";
  document.getElementById("modal-close").textContent = "Schlie\u00dfen";
  document.getElementById("modal-title").textContent = "Fr\u00fchere St\u00e4nde";
  document.getElementById("modal-body").textContent = backups.length
    ? `${backups.length === 1 ? "1 gespeicherter Stand" : backups.length + " gespeicherte St\u00e4nde"} (bis zu 15 lokale St\u00e4nde werden automatisch vorgehalten, \u00e4ltere liegen in Git). Vor jeder Wiederherstellung wird Ihr aktueller Stand gesichert.`
    : "F\u00fcr diese Datei gibt es noch keine lokalen Sicherungen. Sie entstehen automatisch im Hintergrund vor jedem Speichern.";
  const extra = document.getElementById("modal-extra");
  extra.innerHTML = "";
  if (backups.length) {
    const ul = document.createElement("ul");
    ul.className = "backup-list";
    backups.forEach((b, idx) => {
      const li = document.createElement("li");
      const info = document.createElement("div");
      info.title = b.path || b.filename || "";
      const latestBadge = idx === 0 ? `<span class="backup-latest">Neuester</span>` : "";
      info.innerHTML =
        `<div class="backup-title">Stand vom ${escapeHtml(formatTimestamp(b.mtime))}${latestBadge}</div>` +
        `<div class="meta">${escapeHtml(formatBytes(b.size))} \u00b7 ${escapeHtml(friendlyBackupLocation(b.location))}</div>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "secondary";
      btn.textContent = "Wiederherstellen";
      btn.addEventListener("click", () => restoreBackup(b));
      li.appendChild(info);
      li.appendChild(btn);
      ul.appendChild(li);
    });
    extra.appendChild(ul);
  }
  const details = document.createElement("details");
  details.className = "tech-details";
  const summary = document.createElement("summary");
  summary.textContent = "Erweitert (Sicherungsort & Schreibtest)";
  const more = document.createElement("div");
  more.className = "backup-more";
  for (const [label, help, fn] of [
    ["Sicherungsort w\u00e4hlen \u2026", "Neue Sicherungen in einen eigenen Ordner legen (gilt nur f\u00fcr diese Sitzung).", doChooseBackupDir],
    ["Schreibzugriff pr\u00fcfen", "Testet, ob am Sicherungsort und im Dateiordner geschrieben werden kann.", doStorageCheck],
  ]) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secondary";
    btn.textContent = label;
    btn.title = help;
    btn.addEventListener("click", () => {
      hideModal();
      fn();
    });
    more.appendChild(btn);
  }
  details.appendChild(summary);
  details.appendChild(more);
  extra.appendChild(details);
  overlay.classList.remove("hidden");
}

async function restoreBackup(b) {
  const n = pendingCount();
  let msg =
    `Den fr\u00fcheren Stand vom ${formatTimestamp(b.mtime)} wiederherstellen?\n\n` +
    "Ihr aktueller Stand wird zuvor automatisch gesichert.";
  if (n) {
    msg +=
      `\n\nAchtung: ${n === 1 ? "1 Eintrag ist" : n + " Eintr\u00e4ge sind"} noch nicht gespeichert. ` +
      "Beim Wiederherstellen gehen diese nicht gespeicherten \u00c4nderungen verloren.";
  }
  const confirmed = await showConfirmModal("Fr\u00fcheren Stand wiederherstellen?", msg, {
    confirmLabel: "Stand wiederherstellen",
    cancelLabel: "Abbrechen",
    danger: true,
    kind: "warn",
  });
  if (!confirmed) {
    showNothingDone("Wiederherstellen", "Abgebrochen; die Datei bleibt unver\u00e4ndert.");
    return;
  }
  if (n) await discardPendingOnServer();
  showModal("Wiederherstellen \u2026", "Aktueller Stand wird gesichert, dann wird der fr\u00fchere Stand eingespielt.", "progress");
  try {
    const resp = await apiPost("/api/restore", { path: b.path });
    App.state = resp;
    afterFileLoaded();
    showModal(
      "Fr\u00fcherer Stand wiederhergestellt",
      `Der Stand vom ${formatTimestamp(b.mtime)} wurde erfolgreich eingespielt.\n\n` +
        "Ihr bisheriger Stand wurde zuvor automatisch gesichert.",
      "ok"
    );
    appendTechDetails([
      `Wiederhergestellte Datei: ${b.filename}`,
      `Sicherung des vorherigen Stands: ${resp.backup_path}`,
      `Schreibmethode: ${resp.write_method === "atomic" ? "atomar (os.replace)" : "direkter R\u00fcckfall (r+b)"}`,
    ]);
  } catch (err) {
    handleApiError(err, "Wiederherstellung fehlgeschlagen");
  }
}

// ---------------------------------------------------------------------
// Hilfsfunktionen: Text, Zeit, Größen
// ---------------------------------------------------------------------

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(unixSeconds) {
  try {
    return new Date(unixSeconds * 1000).toLocaleString("de-DE");
  } catch {
    return String(unixSeconds);
  }
}

function groupLetterFor(name) {
  if (!name) return "#";
  const ch = name.trim().charAt(0).toUpperCase();
  if ("ÄÖÜ".includes(ch)) return "ÄÖÜ";
  if (ch >= "A" && ch <= "Z") return ch;
  return "#";
}

// ---------------------------------------------------------------------
// Vormerken: Aenderungen mehrerer Eintraege sammeln, gemeinsam speichern
// ---------------------------------------------------------------------

function normalizeSingleLine(s) {
  return String(s || "").replace(/[ \t]*[\r\n]+[ \t]*/g, " ");
}

function collectFormData() {
  return {
    id: document.getElementById("f-id").value.trim(),
    lang: document.getElementById("f-lang").value.trim() || "de",
    type: document.getElementById("f-type").value,
    pref: normalizeSingleLine(document.getElementById("f-pref").value).trim(),
    note: normalizeSingleLine(document.getElementById("f-note").value).trim(),
    synonym: document.getElementById("f-synonym").checked,
    alts: collectAltRows(),
    exact: collectRowValues("exact-list"),
    close: collectRowValues("close-list"),
    related: relatedIds(),
  };
}

// Gleicht Formulardaten mit dem gespeicherten Eintrag ab; gleich = keine Aenderung.
function sameAsRecord(data, rec) {
  const alts = (list) => (list || []).map((a) => (a && typeof a === "object" ? [a.text, a.lang || ""] : [a, ""]));
  const norm = (d) =>
    JSON.stringify([
      d.id, d.lang || "de", d.type, d.pref, d.note || "", !!d.synonym,
      alts(d.alts), d.exact || [], d.close || [], d.related || [],
    ]);
  return norm(data) === norm(rec);
}

// Schluessel aller vorgemerkten Eintraege inkl. des gerade geaenderten Formulars.
function pendingKeys() {
  const keys = new Set(App.drafts.keys());
  if (App.dirty) keys.add(App.currentKey || "__NEW__:current");
  return keys;
}

function pendingCount() {
  return pendingKeys().size;
}

// Uebernimmt das gerade geaenderte Formular in die Vormerkliste (beim Wechsel
// zu einem anderen Eintrag). Ist es wieder identisch mit dem gespeicherten
// Stand, wird die Vormerkung entfernt.
function stashCurrentForm() {
  if (!App.dirty || !App.selectedId) return;
  const isNew = App.selectedId === "__NEW__";
  const rec = isNew ? null : findRecord(App.selectedId);
  if (rec && rec.protected) {
    App.dirty = false;
    return;
  }
  const data = collectFormData();
  let key = App.currentKey;
  if (!key) key = isNew ? "__NEW__:" + ++App.newCounter : App.selectedId;
  if (!isNew && rec && sameAsRecord(data, rec)) {
    App.drafts.delete(key);
  } else {
    App.drafts.set(key, { key, originalId: isNew ? null : App.selectedId, data });
  }
  App.dirty = false;
  App.currentKey = key;
  renderPending();
  renderTree();
}

function draftLabel(d) {
  const name = d.data.pref || d.data.id || "(ohne Bezeichnung)";
  return d.originalId ? name : name + " (neu)";
}

// "Eintrag zuruecksetzen" ist nur aktiv, wenn der GEOEFFNETE Eintrag eine
// nicht gespeicherte Aenderung hat; sonst sagt der Tooltip, warum nicht.
function updateDiscardButton() {
  const btn = document.getElementById("btn-discard");
  const rec = App.selectedId && App.selectedId !== "__NEW__" ? findRecord(App.selectedId) : null;
  const hasChange =
    !!App.selectedId && !(rec && rec.protected) && (App.dirty || !!(App.currentKey && App.drafts.has(App.currentKey)));
  btn.disabled = !hasChange;
  btn.title = hasChange
    ? "Nimmt die \u00c4nderungen an dem Eintrag zur\u00fcck, der gerade ge\u00f6ffnet ist. Andere vorgemerkte Eintr\u00e4ge bleiben erhalten."
    : pendingCount()
      ? "Der ge\u00f6ffnete Eintrag ist unver\u00e4ndert. Die vorgemerkten Eintr\u00e4ge stehen darunter; \u201eAlle verwerfen\u201c nimmt sie alle zur\u00fcck."
      : "Der ge\u00f6ffnete Eintrag ist unver\u00e4ndert.";
}

function renderPending() {
  updateDiscardButton();
  scheduleSync();
  const box = document.getElementById("pending-box");
  const saveBtn = document.getElementById("btn-save");
  const n = pendingCount();
  saveBtn.textContent = n ? `Alle \u00c4nderungen speichern (${n})` : "\u00c4nderungen speichern";
  box.innerHTML = "";
  if (!n) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const lead = document.createElement("span");
  lead.textContent = n === 1 ? "Noch nicht gespeichert:" : `Noch nicht gespeichert (${n} Eintr\u00e4ge):`;
  box.appendChild(lead);
  const shown = [...App.drafts.values()];
  // Das gerade geaenderte, noch nicht vorgemerkte Formular steht mit in der Liste.
  if (App.dirty && !App.drafts.has(App.currentKey || "")) {
    const isNew = App.selectedId === "__NEW__";
    shown.push({
      key: App.currentKey || "__NEW__:current",
      originalId: isNew ? null : App.selectedId,
      data: { id: document.getElementById("f-id").value.trim(), pref: document.getElementById("f-pref").value.trim() },
    });
  }
  for (const d of shown) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className =
      "pending-chip" + (d.key === App.currentKey ? " current" : "") + (App.failedId && d.data.id === App.failedId ? " failed" : "");
    chip.textContent = draftLabel(d);
    chip.title = "Diesen Eintrag \u00f6ffnen";
    chip.addEventListener("click", () => openDraft(d.key));
    box.appendChild(chip);
  }
  const all = document.createElement("button");
  all.type = "button";
  all.className = "subtle";
  all.textContent = "Alle verwerfen";
  all.title = "Nimmt ALLE nicht gespeicherten \u00c4nderungen zur\u00fcck.";
  all.addEventListener("click", discardAll);
  box.appendChild(all);
  const note = document.createElement("span");
  note.className = "pending-note";
  note.textContent = App.persistError
    ? "Zwischensicherung fehlgeschlagen"
    : App.lastPersistTime
      ? `Zwischengesichert um ${App.lastPersistTime}`
      : "Zwischensicherung alle 10 Min.";
  note.title = App.persistError
    ? App.persistError
    : "Vorgemerkte Eintr\u00e4ge werden alle 10 Minuten zus\u00e4tzlich auf der Festplatte zwischengesichert (nicht in der TTL-Datei) und nach einem Absturz beim n\u00e4chsten \u00d6ffnen der Datei angeboten.";
  box.appendChild(note);
}

async function discardAll() {
  const n = pendingCount();
  if (!n) return;
  const confirmed = await showConfirmModal(
    "Alle nicht gespeicherten \u00c4nderungen verwerfen?",
    `Alle ${n} nicht gespeicherten ${n === 1 ? "\u00c4nderung" : "\u00c4nderungen"} wirklich verwerfen?\n\nDie TTL-Datei selbst bleibt unver\u00e4ndert.`,
    {
      confirmLabel: n === 1 ? "1 \u00c4nderung verwerfen" : `Alle ${n} \u00c4nderungen verwerfen`,
      cancelLabel: "Abbrechen",
      danger: true,
    }
  );
  if (!confirmed) {
    showNothingDone("Alle verwerfen", "Abgebrochen; die \u00c4nderungen bleiben erhalten.");
    return;
  }
  const wasNew = App.selectedId === "__NEW__";
  const id = App.selectedId;
  App.drafts.clear();
  App.dirty = false;
  discardPendingOnServer();
  App.lastPersistTime = null;
  if (wasNew) clearEditor();
  else if (id) selectRecordSilently(id);
  renderPending();
  renderTree();
  showBanner(
    `${n} nicht gespeicherte ${n === 1 ? "\u00c4nderung wurde" : "\u00c4nderungen wurden"} verworfen. Die Datei ist unver\u00e4ndert.`,
    "ok"
  );
}

// ---------------------------------------------------------------------
// Zwischensicherung: Vormerkungen an den Server melden / auf Platte sichern
// ---------------------------------------------------------------------

function pendingItems() {
  const map = new Map(App.drafts);
  if (App.dirty && App.selectedId) {
    const isNew = App.selectedId === "__NEW__";
    const rec = isNew ? null : findRecord(App.selectedId);
    if (!(rec && rec.protected)) {
      map.set(App.currentKey || "__NEW__:current", {
        originalId: isNew ? null : App.selectedId,
        data: collectFormData(),
      });
    }
  }
  return [...map.values()].map((d) => ({ original_id: d.originalId, data: d.data }));
}

// Meldet die Vormerkungen (entprellt) an den Server. Der Server braucht sie,
// damit das Startfenster beim Beenden warnen und speichern kann. Auf die
// Platte (Zwischensicherung) geht es alle 10 Minuten, solange etwas vorgemerkt ist.
function scheduleSync() {
  if (!App.syncEnabled || !App.state || !App.state.path) return;
  if (pendingCount() > 0 && App.persistDueAt === null) App.persistDueAt = Date.now() + AUTOSAVE_INTERVAL_MS;
  if (pendingCount() === 0) App.persistDueAt = null;
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => syncPending(false), 1500);
}

async function syncPending(persist) {
  if (!App.syncEnabled || !App.state || !App.state.path) return;
  try {
    const resp = await apiPost("/api/pending", {
      items: pendingItems(),
      version: App.state.sha256,
      persist: !!persist,
    });
    if (persist) {
      if (resp.persisted) {
        App.lastPersistTime = new Date(resp.saved_at * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
        App.persistError = null;
      } else if (resp.persist_error) {
        App.persistError = resp.persist_error;
      }
      App.persistDueAt = null;
      renderPending();
    }
  } catch {
    // Passive Hilfsfunktion: ein Fehler hier darf die Arbeit nicht stoeren.
  }
}

function autosaveTick() {
  if (App.persistDueAt !== null && Date.now() >= App.persistDueAt && pendingCount() > 0) {
    clearTimeout(syncTimer);
    syncPending(true);
  }
}

// Nach dem Laden einer Datei: gibt es eine Zwischensicherung (z. B. nach einem
// Absturz oder einem Beenden ohne Rueckfrage)? Erst danach wird gemeldet.
async function checkRecovery() {
  App.syncEnabled = false;
  try {
    if (!App.state || !App.state.path) return;
    const r = await apiGet("/api/recovery");
    if (r.exists && r.count) showRecoveryDialog(r);
  } catch {
    // keine Zwischensicherung abrufbar: normal weiterarbeiten
  } finally {
    App.syncEnabled = true;
    scheduleSync();
  }
}

function showRecoveryDialog(r) {
  const names = r.items.slice(0, 8).map((it) => {
    const d = it.data || {};
    return "\u2022 " + (d.pref || d.id || "(ohne Bezeichnung)") + (it.original_id ? "" : " (neu)");
  });
  if (r.items.length > 8) names.push(`\u2026 und ${r.items.length - 8} weitere`);
  let body =
    `Von einer fr\u00fcheren Sitzung gibt es eine Zwischensicherung vom ${formatTimestamp(r.saved_at)} mit ` +
    `${r.count} nicht gespeicherten ${r.count === 1 ? "Eintrag" : "Eintr\u00e4gen"}:\n\n${names.join("\n")}\n\n` +
    "Sie wurde nicht in die Datei geschrieben. Wiederherstellen stellt die Eintr\u00e4ge als vorgemerkt wieder her " +
    "(gespeichert wird erst mit \u201eAlle \u00c4nderungen speichern\u201c). Verwerfen l\u00f6scht die Zwischensicherung endg\u00fcltig.";
  if (!r.sha_matches) {
    body +=
      "\n\nHinweis: Die Datei hat sich seit der Zwischensicherung ge\u00e4ndert. Beim Speichern werden die Eintr\u00e4ge " +
      "in den aktuellen Stand eingesetzt; passt etwas nicht, wird nichts geschrieben und der Eintrag genannt.";
  }
  showChoiceModal("Nicht gespeicherte \u00c4nderungen gefunden", body, "warn", [
    { label: "Wiederherstellen", onClick: () => restoreRecovery(r) },
    { label: "Verwerfen", className: "danger", onClick: discardRecovery },
  ], "Sp\u00e4ter entscheiden");
}

function restoreRecovery(r) {
  for (const it of r.items) {
    const key = it.original_id || "__NEW__:" + ++App.newCounter;
    App.drafts.set(key, { key, originalId: it.original_id || null, data: it.data });
  }
  renderTree();
  renderPending();
  showBanner(
    `${r.items.length} ${r.items.length === 1 ? "Eintrag" : "Eintr\u00e4ge"} aus Zwischensicherung wiederhergestellt (\u25cf links). Zum Schreiben \u201eAlle \u00c4nderungen speichern\u201c klicken.`,
    "ok",
    { durationMs: 9000 }
  );
}

async function discardRecovery() {
  try {
    await apiPost("/api/recovery-discard", {});
  } catch (err) {
    handleApiError(err, "Zwischensicherung konnte nicht gel\u00f6scht werden");
  }
}

// Vorgemerkte Aenderungen bewusst verworfen: Zwischensicherung auf dem Server loeschen.
async function discardPendingOnServer() {
  try {
    await apiPost("/api/recovery-discard", {});
  } catch {
    // best effort
  }
}

// Auswahldialog mit mehreren Schaltflaechen (zusaetzlich zum Schliessen-Knopf).
function showChoiceModal(title, body, kind, choices, closeLabel) {
  showModal(title, body, kind);
  document.getElementById("modal-close").textContent = closeLabel || "Abbrechen";
  const extra = document.getElementById("modal-extra");
  extra.innerHTML = "";
  const row = document.createElement("div");
  row.className = "choice-row";
  for (const c of choices) {
    const btn = document.createElement("button");
    btn.type = "button";
    if (c.className) btn.className = c.className;
    btn.textContent = c.label;
    btn.addEventListener("click", () => {
      hideModal();
      c.onClick();
    });
    row.appendChild(btn);
  }
  extra.appendChild(row);
}

function openDraft(key) {
  stashCurrentForm();
  const d = App.drafts.get(key);
  if (!d) return;
  if (d.originalId) {
    jumpToConcept(d.originalId);
  } else {
    App.selectedId = "__NEW__";
    showEditorForm({ ...d.data }, { isNew: true, key });
    renderTree();
  }
}

// Fuer Aktionen, die die geoeffnete Datei wechseln (oeffnen, schliessen):
// nicht gespeicherte Eintraege gehen dabei verloren. Der Text sagt klar,
// was die Aktion tut und was mit den Aenderungen geschieht.
async function confirmDiscardIfDirty(kind) {
  const n = pendingCount();
  if (!n) return true;
  const what = n === 1 ? "1 Eintrag ist" : `${n} Eintr\u00e4ge sind`;
  const texts = {
    open: `${what} noch nicht gespeichert. Beim \u00d6ffnen einer anderen Datei gehen diese \u00c4nderungen verloren.\n\nTrotzdem eine andere Datei \u00f6ffnen?`,
    close: `${what} noch nicht gespeichert. Beim Schlie\u00dfen der Datei gehen diese \u00c4nderungen verloren.\n\nTrotzdem schlie\u00dfen?`,
  };
  const labels = {
    open: "Verwerfen und andere Datei \u00f6ffnen",
    close: "Verwerfen und Datei schlie\u00dfen",
  };
  return showConfirmModal(
    "Nicht gespeicherte \u00c4nderungen",
    texts[kind] || `${what} noch nicht gespeichert. Trotzdem verwerfen?`,
    { confirmLabel: labels[kind] || "Verwerfen", cancelLabel: "Abbrechen", danger: true }
  );
}

function markDirty() {
  App.dirty = true;
  App.saveFailed = false;
  App.justSaved = null;
  updateSaveStatus();
  renderPending();
  markCurrentRowChanged();
  scheduleSynonymCheck(false);
}

function markCurrentRowChanged() {
  if (!App.selectedId) return;
  if (App.selectedId === "__NEW__") {
    const row = document.querySelector("#tree-root .concept-row.draft-new.selected");
    if (row) {
      const prefVal = normalizeSingleLine(document.getElementById("f-pref").value).trim() || "(ohne Bezeichnung)";
      const idVal = document.getElementById("f-id").value.trim();
      const typeVal = document.getElementById("f-type").value || "org";
      const prefEl = row.querySelector(".pref");
      const metaEl = row.querySelector(".meta");
      if (prefEl) prefEl.textContent = prefVal;
      if (metaEl) metaEl.textContent = `${idVal ? "ex:" + idVal : "Kennung noch offen"} \u00b7 ${typeVal} \u00b7 neu`;
    }
    return;
  }
  const node = document.querySelector(`[data-concept-id="${cssEscape(App.selectedId)}"]`);
  if (node) node.classList.add("changed");
}

// ---------------------------------------------------------------------
// Synonymliste (Typesense): dieselbe Benennung bei zwei Konzepten
// ---------------------------------------------------------------------
// Die Pruefung laeuft im Server (dort steht der Graph der ganzen Datei, auch
// mit geschuetzten Bloecken). Hier nur: anstossen, entprellen, anzeigen.
// Rein passive Hilfsanzeige -> bei Fehlern bewusst kein Dialog.

let synTimer = null;
let synSeq = 0;

function scheduleSynonymCheck(immediate) {
  clearTimeout(synTimer);
  synTimer = setTimeout(runSynonymCheck, immediate ? 0 : 450);
}

function clearSynonymBox() {
  const box = document.getElementById("syn-check");
  box.className = "syn-check";
  box.textContent = "";
}

async function runSynonymCheck() {
  const seq = ++synSeq;
  const rec = App.selectedId && App.selectedId !== "__NEW__" ? findRecord(App.selectedId) : null;
  const synBox = document.getElementById("f-synonym");
  if (!App.state || !App.state.path || !App.selectedId || (rec && rec.protected) || !synBox.checked) {
    clearSynonymBox();
    return;
  }
  const isNew = App.selectedId === "__NEW__";
  // Weitere vorgemerkte Eintraege mitschicken, damit Kollisionen zwischen zwei
  // noch nicht gespeicherten Eintraegen schon waehrend der Eingabe auffallen.
  const otherDrafts = [];
  for (const [key, d] of App.drafts.entries()) {
    if (key === App.currentKey) continue;
    if (!isNew && d.originalId === App.selectedId) continue;
    otherDrafts.push({
      key,
      original_id: d.originalId,
      data: {
        id: (d.data && d.data.id) || "",
        lang: (d.data && d.data.lang) || "de",
        pref: (d.data && d.data.pref) || "",
        synonym: !!(d.data && d.data.synonym),
        alts: (d.data && d.data.alts) || [],
      },
    });
  }
  let resp;
  try {
    resp = await apiPost("/api/synonym-check", {
      original_id: isNew ? null : App.selectedId,
      data: {
        id: document.getElementById("f-id").value.trim(),
        lang: document.getElementById("f-lang").value.trim() || "de",
        pref: normalizeSingleLine(document.getElementById("f-pref").value).trim(),
        synonym: true,
        alts: collectAltRows(),
      },
      drafts: otherDrafts,
    });
  } catch {
    return;
  }
  if (seq !== synSeq) return; // veraltete Antwort
  renderSynonymConflicts(resp.conflicts || []);
}

function renderSynonymConflicts(conflicts) {
  const box = document.getElementById("syn-check");
  box.innerHTML = "";
  box.className = "syn-check";
  if (!conflicts.length) return;
  const blocking = conflicts.some((c) => c.is_new);
  box.classList.add(blocking ? "error" : "warn");

  const head = document.createElement("div");
  head.className = "syn-head";
  head.textContent = blocking
    ? "Speichern nicht m\u00f6glich: Diese Benennung steht schon bei einem anderen Konzept der Synonymliste."
    : "Bereits vorhandene Kollision (blockiert das Speichern nicht, sollte aber bereinigt werden):";
  box.appendChild(head);

  const ul = document.createElement("ul");
  for (const c of conflicts) {
    const li = document.createElement("li");
    const isUnnamedNewDraft = c.in_draft && String(c.other_id || "").startsWith("__NEW__:");
    const targetDesc = isUnnamedNewDraft
      ? "einem neuen, noch nicht gespeicherten Eintrag" +
        (c.other_pref && !String(c.other_pref).startsWith("__NEW__:") ? ` (${c.other_pref})` : "")
      : `ex:${c.other_id} (${c.other_pref})` + (c.in_draft ? " [vorgemerkte \u00c4nderung]" : "");
    let text = `\u201e${c.label}\u201c steht auch bei ${targetDesc}`;
    if (c.other_label !== c.label) text += `, dort als \u201e${c.other_label}\u201c (Gro\u00df-/Kleinschreibung z\u00e4hlt nicht als Unterschied)`;
    li.appendChild(document.createTextNode(text + ". "));
    if (blocking && !c.is_new) {
      const old = document.createElement("span");
      old.className = "syn-old";
      old.textContent = "(schon vorher vorhanden) ";
      li.appendChild(old);
    }
    const open = document.createElement("button");
    open.type = "button";
    open.className = "subtle";
    open.textContent = "Eintrag \u00f6ffnen";
    open.addEventListener("click", () => {
      if (c.draft_key && App.drafts.has(c.draft_key)) openDraft(c.draft_key);
      else jumpToConcept(c.other_id);
    });
    li.appendChild(open);
    ul.appendChild(li);
  }
  box.appendChild(ul);

  const how = document.createElement("div");
  how.textContent =
    "Sonst findet die Suche beide Konzepte. L\u00f6sung: die Benennung bei einem der beiden Konzepte entfernen " +
    "oder bei einem den Haken \u201eIn Synonymliste verwenden\u201c wegnehmen.";
  box.appendChild(how);
}

// Dauerhafte Anzeige neben "Aenderungen speichern". Zeigt nur, was der Editor
// wirklich weiss: Formular geaendert / letzter Speichervorgang erfolgreich
// (Sicherung erst nach erfolgreicher, gepruefter Sicherung vom Server gemeldet).
function updateSaveStatus() {
  const el = document.getElementById("save-status");
  el.className = "save-status";
  el.textContent = "";
  if (!App.state || !App.state.path || !App.selectedId) return;
  const rec = App.selectedId !== "__NEW__" ? findRecord(App.selectedId) : null;
  if (rec && rec.protected) return;
  if (App.saveFailed) {
    el.classList.add("failed");
    el.textContent = "Speichern fehlgeschlagen \u2014 die \u00c4nderungen sind noch nicht gespeichert";
  } else if (App.dirty || (App.currentKey && App.drafts.has(App.currentKey))) {
    el.classList.add("unsaved");
    el.textContent = "\u25cf Noch nicht gespeichert";
  } else if (App.justSaved && App.justSaved.ids.includes(App.selectedId)) {
    el.classList.add("saved");
    el.textContent =
      `Gespeichert um ${App.justSaved.time}` +
      (App.justSaved.atomic ? "" : " \u00b7 direkt \u00fcberschrieben (siehe Meldung)");
  } else if (App.selectedId === "__NEW__") {
    el.textContent = "Neuer Eintrag \u2014 noch nicht gespeichert";
  } else {
    el.textContent = pendingCount() ? "Dieser Eintrag ist unver\u00e4ndert" : "Keine ungespeicherten \u00c4nderungen";
  }
}

// Sicherungsstatus als dezenter Tooltip auf dem Button "Fruehere Staende ...".
async function refreshBackupStatus() {
  const btn = document.getElementById("btn-backup-menu");
  if (!btn) return;
  if (!App.state || !App.state.path) {
    btn.title = "Zeigt fr\u00fchere lokale St\u00e4nde dieser Datei (erst Datei \u00f6ffnen).";
    return;
  }
  try {
    const resp = await apiGet("/api/backups");
    const list = resp.backups || [];
    btn.title = list.length
      ? `Fr\u00fchere lokale St\u00e4nde anzeigen (${list.length} vorhanden, neuester: ${formatTimestamp(Math.max(...list.map((b) => b.mtime)))}).`
      : "Noch keine lokale Sicherung f\u00fcr diese Datei vorhanden.";
  } catch {
    btn.title = "Fr\u00fchere lokale St\u00e4nde dieser Datei anzeigen.";
  }
}

// ---------------------------------------------------------------------
// Konzeptverzeichnis (Baumansicht)
// ---------------------------------------------------------------------

function matchesFilter(r, term, typeFilter) {
  if (typeFilter) {
    if (r.protected || r.type !== typeFilter) return false;
  }
  if (!term) return true;
  const altTexts = (r.alts || []).map((a) => (a && typeof a === "object" ? a.text : a));
  const hay = [r.id, r.pref, ...altTexts, ...(r.exact || []), ...(r.close || []), ...(r.related || [])]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(term);
}

function newDraftEntries() {
  const list = [];
  for (const d of App.drafts.values()) {
    if (!d.originalId) list.push(d);
  }
  if (App.selectedId === "__NEW__" && (!App.currentKey || !App.drafts.has(App.currentKey))) {
    list.push({
      key: App.currentKey || "__NEW__:current",
      originalId: null,
      data: {
        id: document.getElementById("f-id").value.trim(),
        pref: normalizeSingleLine(document.getElementById("f-pref").value).trim(),
        type: document.getElementById("f-type").value || "org",
      },
      isCurrentOnly: true,
    });
  }
  return list;
}

function renderTree() {
  const root = document.getElementById("tree-root");
  root.innerHTML = "";

  const hasFile = !!(App.state && App.state.path);
  const term = document.getElementById("tree-search").value.trim().toLowerCase();
  const typeFilter = document.getElementById("tree-type-filter").value;
  const records = App.state ? App.state.records : [];
  const visible = records.filter((r) => matchesFilter(r, term, typeFilter));
  const newDrafts = hasFile ? newDraftEntries() : [];

  document.getElementById("tree-counter").textContent = hasFile
    ? `${visible.length} / ${records.length} Konzepte` + (newDrafts.length ? ` (+${newDrafts.length} neu)` : "")
    : "0 / 0 Konzepte";

  if (!hasFile) {
    const empty = document.createElement("div");
    empty.className = "tree-empty";
    empty.textContent = "Noch keine Datei ge\u00f6ffnet.";
    root.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();

  // Neue, noch nicht gespeicherte Eintraege oben sichtbar halten.
  if (newDrafts.length) {
    const groupDiv = document.createElement("div");
    groupDiv.className = "letter-group draft-new-group";
    const header = document.createElement("div");
    header.className = "letter-header";
    header.innerHTML = `<span>Neu (noch nicht gespeichert)</span><span>${newDrafts.length}</span>`;
    const body = document.createElement("div");
    body.className = "letter-body";
    for (const d of newDrafts) {
      const row = document.createElement("div");
      const isSelected = App.selectedId === "__NEW__" && (d.isCurrentOnly || d.key === App.currentKey);
      row.className = "concept-row draft-new changed" + (isSelected ? " selected" : "");
      const prefText = d.data.pref || "(ohne Bezeichnung)";
      const idText = d.data.id ? `ex:${d.data.id}` : "Kennung noch offen";
      row.innerHTML =
        `<div class="pref">${escapeHtml(prefText)}</div>` +
        `<div class="meta">${escapeHtml(idText)} \u00b7 ${escapeHtml(d.data.type || "org")} \u00b7 neu</div>`;
      if (!d.isCurrentOnly) {
        row.addEventListener("click", () => openDraft(d.key));
      }
      body.appendChild(row);
    }
    groupDiv.appendChild(header);
    groupDiv.appendChild(body);
    frag.appendChild(groupDiv);
  }

  if (!visible.length && !newDrafts.length) {
    const empty = document.createElement("div");
    empty.className = "tree-empty";
    empty.textContent = records.length
      ? "Keine passenden Eintr\u00e4ge gefunden. Suche oder Typfilter zur\u00fccksetzen."
      : "Die Datei enth\u00e4lt noch keine Konzepte.";
    frag.appendChild(empty);
    root.appendChild(frag);
    return;
  }

  const groups = {};
  for (const r of visible) {
    const label = r.protected ? r.id : (r.pref || r.id);
    const letter = groupLetterFor(label);
    (groups[letter] = groups[letter] || []).push(r);
  }

  const forceExpand = Boolean(term || typeFilter);
  const order = (l) => (l === "#" ? 2 : l === "ÄÖÜ" ? 1 : 0);
  const letters = Object.keys(groups).sort((a, b) => {
    const oa = order(a), ob = order(b);
    if (oa !== ob) return oa - ob;
    return a.localeCompare(b, "de");
  });

  for (const letter of letters) {
    const group = groups[letter];
    group.sort((a, b) => {
      const la = a.protected ? a.id : (a.pref || a.id);
      const lb = b.protected ? b.id : (b.pref || b.id);
      return la.localeCompare(lb, "de");
    });

    const groupDiv = document.createElement("div");
    groupDiv.className = "letter-group";

    const header = document.createElement("div");
    header.className = "letter-header";
    header.innerHTML = `<span>${escapeHtml(letter)}</span><span>${group.length}</span>`;

    const body = document.createElement("div");
    const collapsed = !forceExpand && !App.expandedLetters.has(letter);
    body.className = "letter-body" + (collapsed ? " collapsed" : "");

    header.addEventListener("click", () => {
      if (App.expandedLetters.has(letter)) App.expandedLetters.delete(letter);
      else App.expandedLetters.add(letter);
      renderTree();
    });

    for (const r of group) {
      const row = document.createElement("div");
      row.className =
        "concept-row" + (r.protected ? " protected" : "") + (App.selectedId === r.id ? " selected" : "") +
        (App.drafts.has(r.id) || (App.dirty && App.currentKey === r.id) ? " changed" : "");
      // Marker, damit ein Befund im rechten Panel gezielt zu dieser Zeile
      // scrollen kann (siehe jumpToConcept).
      row.setAttribute("data-concept-id", r.id);
      const prefText = r.protected ? r.id : r.pref || "(ohne Bezeichnung)";
      const typeCode = r.protected ? "?" : (r.type || "?");
      const typeClass = r.protected ? "" : ` t-${escapeHtml(r.type || "")}`;
      row.innerHTML =
        `<div class="pref">${escapeHtml(prefText)}</div>` +
        `<div class="meta"><span>ex:${escapeHtml(r.id)}</span><span class="type-pill${typeClass}">${escapeHtml(typeCode)}</span></div>`;
      row.addEventListener("click", () => selectRecord(r.id));
      body.appendChild(row);
    }

    groupDiv.appendChild(header);
    groupDiv.appendChild(body);
    frag.appendChild(groupDiv);
  }
  root.appendChild(frag);
}

// ---------------------------------------------------------------------
// Editorformular & Bedienelemente je nach Dateizustand
// ---------------------------------------------------------------------

function updateFileControls() {
  const hasFile = !!(App.state && App.state.path);
  const noFileIds = [
    "btn-close-file", "btn-validate-file", "btn-backup-menu",
    "btn-new-entry", "btn-save",
    "tree-search", "tree-type-filter", "btn-clear-search", "btn-expand-all", "btn-collapse-all",
  ];
  for (const id of noFileIds) {
    const el = document.getElementById(id);
    if (el) el.disabled = !hasFile;
  }
  const delBtn = document.getElementById("btn-delete");
  if (delBtn) {
    const canDelete = hasFile && !!currentDeleteTargetId;
    delBtn.disabled = !canDelete;
    delBtn.title = !hasFile
      ? "Erst eine Datei \u00f6ffnen."
      : canDelete
        ? "L\u00f6scht diesen Eintrag nach Sicherheitsabfrage und Sicherung."
        : "Zuerst links einen gespeicherten Eintrag ausw\u00e4hlen.";
  }
  const welcomeNoFile = document.getElementById("welcome-no-file");
  const welcomeNoSel = document.getElementById("welcome-no-selection");
  if (welcomeNoFile && welcomeNoSel) {
    welcomeNoFile.hidden = hasFile;
    welcomeNoSel.hidden = !hasFile;
  }
}

function clearEditor() {
  document.getElementById("editor-empty").style.display = "block";
  document.getElementById("editor-form").style.display = "none";
  App.selectedId = null;
  App.currentKey = null;
  App.touchedFields.clear();
  currentDeleteTargetId = null;
  updateFileControls();
  renderPending();
  renderSaveHint();
  updateSaveStatus();
  scheduleSynonymCheck(true);
}

function isValidHttpUrl(val) {
  return /^https?:\/\/\S+$/i.test(String(val || "").trim());
}

function fillRowList(containerId, values, placeholder) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  const list = values && values.length ? values : [""];
  list.forEach((v) => addRow(containerId, v, placeholder));
}

function addRow(containerId, value, placeholder) {
  const container = document.getElementById(containerId);
  const isAlt = containerId === "alt-list";
  const isLink = !isAlt;

  const wrapper = isLink ? document.createElement("div") : null;
  if (wrapper) wrapper.className = "link-item";

  const row = document.createElement("div");
  row.className = isAlt ? "alt-row" : "link-row";

  // altLabels tragen ihr EIGENES Sprachkennzeichen. Ohne dieses Feld wurden
  // beim Speichern alle altLabels auf die Sprache des prefLabel gesetzt,
  // wodurch z. B. "@en"-Benennungen still zu "@de" wurden.
  const text = value && typeof value === "object" ? value.text : value;
  const lang = value && typeof value === "object" ? value.lang : "";

  const input = document.createElement("input");
  input.type = isLink ? "url" : "text";
  input.className = "row-text";
  input.value = text || "";
  input.placeholder = placeholder || "";
  input.addEventListener("input", markDirty);

  let langInput = null;
  if (isAlt) {
    langInput = document.createElement("input");
    langInput.type = "text";
    langInput.className = "row-lang mono";
    langInput.maxLength = 8;
    langInput.value = lang || document.getElementById("f-lang").value.trim() || "de";
    langInput.title = "Sprachkennzeichen dieser Benennung, z. B. de oder en";
    langInput.placeholder = "de";
    langInput.addEventListener("input", markDirty);
  }

  let openBtn = null;
  let errEl = null;
  let checkUrl = null;
  if (isLink) {
    openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "row-open-link";
    openBtn.textContent = "\u00d6ffnen \u2197";
    openBtn.title = "Internetadresse im Browser \u00f6ffnen, um den Link zu pr\u00fcfen";
    openBtn.addEventListener("click", () => {
      const url = input.value.trim();
      if (isValidHttpUrl(url)) window.open(url, "_blank", "noopener,noreferrer");
    });

    errEl = document.createElement("p");
    errEl.className = "field-check";

    checkUrl = () => {
      const v = input.value.trim();
      const valid = isValidHttpUrl(v);
      openBtn.disabled = !valid;
      if (v && !valid) {
        input.classList.add("invalid");
        errEl.className = "field-check error";
        errEl.textContent = "Ung\u00fcltige Internetadresse \u2014 muss mit https:// oder http:// beginnen.";
      } else {
        input.classList.remove("invalid");
        errEl.className = "field-check";
        errEl.textContent = "";
      }
    };
    input.addEventListener("input", checkUrl);
    input.addEventListener("blur", checkUrl);
    checkUrl();
  }

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "row-remove";
  removeBtn.textContent = "\u2715";
  removeBtn.title = "Zeile leeren / entfernen";
  removeBtn.addEventListener("click", () => {
    const itemEl = wrapper || row;
    // Bleibt es die einzige Zeile, wird sie geleert statt komplett geloescht,
    // damit das Eingabefeld immer sofort zum Eintippen bereitsteht.
    if (container.children.length <= 1) {
      const hadVal = !!input.value.trim();
      input.value = "";
      if (langInput) langInput.value = document.getElementById("f-lang").value.trim() || "de";
      if (checkUrl) checkUrl();
      if (hadVal) markDirty();
      input.focus();
      return;
    }
    itemEl.remove();
    markDirty();
  });

  row.appendChild(input);
  if (langInput) row.appendChild(langInput);
  if (openBtn) row.appendChild(openBtn);
  row.appendChild(removeBtn);

  if (wrapper) {
    wrapper.appendChild(row);
    wrapper.appendChild(errEl);
    container.appendChild(wrapper);
    return wrapper;
  }
  container.appendChild(row);
  return row;
}

// ---------------------------------------------------------------------
// Verwandte Konzepte: Auswahl statt ID-Eingabe
// ---------------------------------------------------------------------

const RELATED_MAX_RESULTS = 8;
let relatedActive = -1;   // Index des per Pfeiltaste markierten Treffers
let relatedShown = [];    // aktuell angezeigte Treffer (nur waehlbare)

function relatedIds() {
  return Array.from(document.querySelectorAll("#related-list .related-row")).map((r) => r.dataset.id);
}

function recordLabel(rec) {
  return rec.protected ? "" : rec.pref || "";
}

function addRelatedRow(id) {
  if (relatedIds().includes(id)) return;
  const rec = findRecord(id);
  const row = document.createElement("div");
  row.className = "related-row" + (rec ? "" : " missing");
  row.dataset.id = id;

  const info = document.createElement("div");
  info.className = "related-info";
  if (rec) {
    const nameBtn = document.createElement("button");
    nameBtn.type = "button";
    nameBtn.className = "related-name-btn";
    nameBtn.textContent = recordLabel(rec) || id;
    nameBtn.title = `Zum verkn\u00fcpften Eintrag \u201e${id}\u201c springen`;
    nameBtn.addEventListener("click", () => jumpToConcept(id));
    info.appendChild(nameBtn);
  } else {
    const name = document.createElement("span");
    name.className = "related-name";
    name.textContent = id;
    info.appendChild(name);
  }
  const meta = document.createElement("span");
  meta.className = "related-meta";
  meta.textContent = rec
    ? `ex:${id}` + (rec.type ? ` \u00b7 ${rec.type}` : "") + (rec.protected ? " \u00b7 gesch\u00fctzter Eintrag" : "")
    : `ex:${id} \u00b7 in dieser Datei nicht gefunden`;
  info.appendChild(meta);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "row-remove";
  removeBtn.textContent = "\u2715";
  removeBtn.title = "Diese Verkn\u00fcpfung entfernen";
  removeBtn.setAttribute("aria-label", `Verkn\u00fcpfung mit ${id} entfernen`);
  removeBtn.addEventListener("click", () => {
    row.remove();
    markDirty();
  });

  row.appendChild(info);
  row.appendChild(removeBtn);
  document.getElementById("related-list").appendChild(row);
}

function fillRelated(ids) {
  document.getElementById("related-list").innerHTML = "";
  (ids || []).forEach(addRelatedRow);
  closeRelatedResults();
  document.getElementById("related-search").value = "";
}

// Treffer: Kennung, Benennung oder Alternativbenennung enthaelt den Suchtext.
// Ausgeschlossen: das Konzept selbst und bereits gewaehlte Konzepte.
function relatedCandidates(term) {
  const t = term.trim().toLowerCase();
  if (!t || !App.state) return [];
  const own = document.getElementById("f-id").value.trim();
  const chosen = new Set(relatedIds());
  const out = [];
  for (const r of App.state.records) {
    if (r.id === own || chosen.has(r.id)) continue;
    const label = recordLabel(r);
    const alts = r.protected ? [] : (r.alts || []).map((a) => (typeof a === "string" ? a : a.text)).filter(Boolean);
    const idL = r.id.toLowerCase();
    const labL = label.toLowerCase();
    const altHit = alts.find((a) => a.toLowerCase().includes(t));
    if (!idL.includes(t) && !labL.includes(t) && !altHit) continue;
    let rank = 3;
    if (idL === t) rank = 0;
    else if (labL.startsWith(t) || idL.startsWith(t)) rank = 1;
    else if (labL.includes(t)) rank = 2;
    out.push({ rec: r, label, rank, viaAlt: !labL.includes(t) && !idL.includes(t) ? altHit : null });
  }
  out.sort((a, b) => a.rank - b.rank || (a.label || a.rec.id).localeCompare(b.label || b.rec.id, "de"));
  return out;
}

function closeRelatedResults() {
  const ul = document.getElementById("related-results");
  ul.hidden = true;
  ul.innerHTML = "";
  document.getElementById("related-search").setAttribute("aria-expanded", "false");
  relatedShown = [];
  relatedActive = -1;
}

function highlightRelated(index) {
  const items = document.querySelectorAll("#related-results li[data-pick]");
  items.forEach((li, i) => li.classList.toggle("active", i === index));
  relatedActive = index;
  if (items[index]) items[index].scrollIntoView({ block: "nearest" });
}

function renderRelatedResults() {
  const input = document.getElementById("related-search");
  const ul = document.getElementById("related-results");
  const term = input.value;
  if (!term.trim()) {
    closeRelatedResults();
    return;
  }
  const all = relatedCandidates(term);
  ul.innerHTML = "";
  relatedShown = all.slice(0, RELATED_MAX_RESULTS);

  relatedShown.forEach((c, i) => {
    const li = document.createElement("li");
    li.dataset.pick = c.rec.id;
    li.setAttribute("role", "option");
    const name = document.createElement("span");
    name.className = "r-name";
    name.textContent = c.label || c.rec.id;
    const meta = document.createElement("span");
    meta.className = "r-meta";
    meta.textContent =
      `ex:${c.rec.id}` + (c.rec.type ? ` \u00b7 ${c.rec.type}` : "") + (c.rec.protected ? " \u00b7 gesch\u00fctzt" : "") +
      (c.viaAlt ? ` \u00b7 auch bekannt als: ${c.viaAlt}` : "");
    li.appendChild(name);
    li.appendChild(meta);
    // mousedown statt click, damit das Feld vorher nicht den Fokus verliert.
    li.addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      chooseRelated(c.rec.id);
    });
    li.addEventListener("mousemove", () => highlightRelated(i));
    ul.appendChild(li);
  });

  if (!all.length) {
    const li = document.createElement("li");
    li.className = "note";
    li.textContent = "Kein passendes Konzept gefunden.";
    ul.appendChild(li);
  } else if (all.length > relatedShown.length) {
    const li = document.createElement("li");
    li.className = "note";
    li.textContent = `${all.length - relatedShown.length} weitere Treffer \u2014 Suchtext eingrenzen.`;
    ul.appendChild(li);
  }
  ul.hidden = false;
  input.setAttribute("aria-expanded", "true");
  highlightRelated(relatedShown.length ? 0 : -1);
}

function chooseRelated(id) {
  addRelatedRow(id);
  markDirty();
  const input = document.getElementById("related-search");
  input.value = "";
  closeRelatedResults();
  input.focus();
}

function setupRelatedPicker() {
  const input = document.getElementById("related-search");
  // Tippen im Suchfeld ist noch keine Aenderung am Eintrag: die Ereignisse
  // duerfen nicht bis zum Formular durchlaufen (dort steht markDirty).
  input.addEventListener("input", (ev) => {
    ev.stopPropagation();
    renderRelatedResults();
  });
  input.addEventListener("change", (ev) => ev.stopPropagation());
  input.addEventListener("keydown", (ev) => {
    const open = !document.getElementById("related-results").hidden;
    if (ev.key === "ArrowDown" && relatedShown.length) {
      ev.preventDefault();
      if (!open) renderRelatedResults();
      else highlightRelated((relatedActive + 1) % relatedShown.length);
    } else if (ev.key === "ArrowUp" && open && relatedShown.length) {
      ev.preventDefault();
      highlightRelated((relatedActive - 1 + relatedShown.length) % relatedShown.length);
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      if (open && relatedShown[relatedActive]) chooseRelated(relatedShown[relatedActive].rec.id);
    } else if (ev.key === "Escape" && open) {
      ev.preventDefault();
      ev.stopPropagation();
      closeRelatedResults();
    }
  });
  input.addEventListener("blur", closeRelatedResults);
  // Klick auf Trefferliste/Scrollleiste soll das Suchfeld nicht verlassen.
  document.getElementById("related-results").addEventListener("mousedown", (ev) => ev.preventDefault());
}

function collectRowValues(containerId) {
  return Array.from(document.querySelectorAll(`#${containerId} input.row-text`))
    .map((i) => i.value.trim())
    .filter(Boolean);
}

function collectAltRows() {
  return Array.from(document.querySelectorAll("#alt-list .alt-row"))
    .map((row) => {
      const textEl = row.querySelector("input.row-text");
      const langEl = row.querySelector("input.row-lang");
      return {
        text: textEl ? textEl.value.trim() : "",
        lang: (langEl ? langEl.value.trim() : "") || "de",
      };
    })
    .filter((a) => a.text);
}

// Bekannte Felder, nur fuer den Tippfehler-Hinweis (Liste = KNOWN_PREDICATES
// in fpv_core.py).
const KNOWN_FIELDS = [
  "skos:prefLabel", "skos:altLabel", "skos:notation", "ex:useInSynonymList",
  "skos:exactMatch", "skos:closeMatch", "skos:note", "skos:related",
];

function editDistance(a, b) {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
  }
  return d[a.length][b.length];
}

function similarKnownField(pred) {
  const p = pred.toLowerCase();
  return (
    KNOWN_FIELDS.find((k) => p !== k.toLowerCase() && (p.startsWith(k.toLowerCase()) || k.toLowerCase().startsWith(p))) ||
    KNOWN_FIELDS.find((k) => editDistance(p, k.toLowerCase()) <= 2) ||
    null
  );
}

// Verstaendlicher Text zu einem geschuetzten Block: was ist los, ist der
// Eintrag bearbeitbar, was tun? Grundlage ist der vom Server gemeldete Grund.
function explainProtected(rec) {
  const reason = rec.protect_reason || "";
  const where = rec.line ? ` Der Eintrag beginnt in Zeile ${rec.line} der Datei.` : "";
  const base = "Dieser Eintrag l\u00e4sst sich im Formular nicht bearbeiten, ";
  const editorOnly = " Er kann nur in einem Texteditor bearbeitet werden; danach die Datei neu \u00f6ffnen.";
  const del = " Das L\u00f6schen des Eintrags bleibt m\u00f6glich, sofern kein anderer Eintrag darauf verweist.";
  let m;
  if ((m = reason.match(/Unbekanntes Pr\u00e4dikat im Block: '(.+)'/))) {
    const sim = similarKnownField(m[1]);
    return (
      base + `weil er das Feld \u201e${m[1]}\u201c enth\u00e4lt, das der Editor nicht kennt.` +
      (sim ? ` M\u00f6glicherweise ist das ein Tippfehler f\u00fcr \u201e${sim}\u201c \u2014 dann bitte im Texteditor korrigieren und die Datei neu \u00f6ffnen.` : editorOnly) +
      where + del
    );
  }
  if (/dreifach/.test(reason)) {
    return base + "weil er einen mehrzeiligen Text in dreifachen Anf\u00fchrungszeichen enth\u00e4lt, der beim Speichern \u00fcber das Formular verloren gehen k\u00f6nnte." + editorOnly + where + del;
  }
  if (/'#'|Kommentar/.test(reason)) {
    return base + "weil im Block ein Kommentar (#) steht, der beim Speichern \u00fcber das Formular verloren gehen w\u00fcrde." + editorOnly + where + del;
  }
  if ((m = reason.match(/(\d+) skos:prefLabel/))) {
    return base + `weil er ${m[1]} bevorzugte Benennungen enth\u00e4lt; das Formular kennt nur eine.` + " Bitte im Texteditor auf eine reduzieren und die Datei neu \u00f6ffnen." + where + del;
  }
  if ((m = reason.match(/(\d+) skos:notation/))) {
    return base + `weil er ${m[1]} Typangaben (skos:notation) enth\u00e4lt; das Formular kennt nur eine.` + " Bitte im Texteditor auf eine reduzieren und die Datei neu \u00f6ffnen." + where + del;
  }
  if (/skos:related/.test(reason)) {
    return base + "weil eine Verkn\u00fcpfung (skos:related) nicht die Form ex:ID hat, etwa eine vollst\u00e4ndige Internetadresse." + editorOnly + where + del;
  }
  return base + `Grund: ${reason || "unbekannt"}` + editorOnly + where + del;
}

// Kurzfassung fuer die Befundliste rechts; die ausfuehrliche Erklaerung steht
// beim Eintrag selbst.
function protectedShort(rec) {
  const reason = rec.protect_reason || "";
  const head = "Nicht im Formular bearbeitbar: ";
  let m;
  if ((m = reason.match(/Unbekanntes Pr\u00e4dikat im Block: '(.+)'/))) {
    const sim = similarKnownField(m[1]);
    return head + `unbekanntes Feld \u201e${m[1]}\u201c` + (sim ? ` \u2014 Tippfehler f\u00fcr \u201e${sim}\u201c?` : ".");
  }
  if (/dreifach/.test(reason)) return head + "mehrzeiliger Text in dreifachen Anf\u00fchrungszeichen.";
  if (/'#'|Kommentar/.test(reason)) return head + "enth\u00e4lt einen Kommentar (#).";
  if ((m = reason.match(/(\d+) skos:prefLabel/))) return head + `${m[1]} bevorzugte Benennungen.`;
  if ((m = reason.match(/(\d+) skos:notation/))) return head + `${m[1]} Typangaben.`;
  if (/skos:related/.test(reason)) return head + "Verkn\u00fcpfung nicht in der Form ex:ID.";
  return head + (reason || "Grund unbekannt.");
}

function showProtectedEditor(rec) {
  document.getElementById("editor-empty").style.display = "none";
  document.getElementById("editor-form").style.display = "block";
  document.getElementById("editor-title").textContent = rec.id;
  document.getElementById("editor-subline").textContent =
    `ex:${rec.id} \u00b7 gesch\u00fctzter Block` + (rec.line ? ` \u00b7 ab Zeile ${rec.line}` : "");

  const notice = document.getElementById("protected-notice");
  notice.style.display = "block";
  notice.textContent = explainProtected(rec);

  // Quelltext des Blocks anzeigen, damit erkennbar ist, WAS genau das
  // Problem verursacht — vorher blieb der Block komplett unsichtbar.
  const rawWrap = document.getElementById("protected-raw-wrap");
  const rawPre = document.getElementById("protected-raw");
  if (rec.raw) {
    rawPre.textContent = "";
    const badPred = ((rec.protect_reason || "").match(/Unbekanntes Pr\u00e4dikat im Block: '(.+)'/) || [])[1];
    rec.raw.split("\n").forEach((line) => {
      const span = document.createElement("span");
      span.textContent = line;
      if (badPred && line.trim().startsWith(badPred + " ")) span.className = "bad-line";
      rawPre.appendChild(span);
    });
    rawWrap.style.display = "block";
  } else {
    rawPre.textContent = "";
    rawWrap.style.display = "none";
  }

  document.getElementById("concept-form").classList.add("protected-mode");
  currentDeleteTargetId = rec.id;
  updateFileControls();
  renderSaveHint();
  updateSaveStatus();
  scheduleSynonymCheck(true);
}

// Sofort-Hinweis fuer Pflichtfelder (Bevorzugte Benennung, Kurzbeschreibung).
// Bei einer frischen Neuanlage erscheinen Hinweise erst, nachdem das Feld
// beruehrt oder verlassen wurde — bei bestehenden Eintraegen mit Luecken sofort.
function updateFieldChecks(forceAll) {
  const isNew = App.selectedId === "__NEW__";
  const checks = [
    { id: "f-pref", boxId: "pref-check", msg: "Pflichtfeld: Bitte eine bevorzugte Benennung eintragen." },
    { id: "f-note", boxId: "note-check", msg: "Pflichtfeld: Bitte eine kurze Erl\u00e4uterung eintragen (erscheint als Mouseover)." },
  ];
  for (const c of checks) {
    const input = document.getElementById(c.id);
    const box = document.getElementById(c.boxId);
    if (!input || !box) continue;
    const val = normalizeSingleLine(input.value).trim();
    const shouldWarn = !val && (forceAll || !isNew || App.touchedFields.has(c.id));
    input.classList.toggle("invalid", shouldWarn);
    box.className = shouldWarn ? "field-check error" : "field-check";
    box.textContent = shouldWarn ? c.msg : "";
  }
}

// Sofort-Hinweis bei der Neuanlage: Format + Eindeutigkeit der Kennung.
// Massgeblich bleibt die Pruefung im Server; das hier erspart den Umweg
// ueber eine Fehlermeldung nach dem Speichern.
function updateIdCheck() {
  const box = document.getElementById("id-check");
  const input = document.getElementById("f-id");
  box.textContent = "";
  box.className = "id-check";
  input.classList.remove("invalid");
  if (App.selectedId !== "__NEW__" || !App.state) return;
  const id = input.value.trim();
  if (!id) {
    if (App.touchedFields.has("f-id")) {
      input.classList.add("invalid");
      box.classList.add("error");
      box.textContent = "Pflichtfeld: Bitte eine eindeutige Kennung eintragen (z. B. ABB).";
    }
    return;
  }
  if (!ID_RE.test(id)) {
    input.classList.add("invalid");
    box.classList.add("error");
    box.textContent = "Ung\u00fcltige Kennung: nur Buchstaben ohne Umlaute, Ziffern sowie . _ - (Anfang: Buchstabe oder _).";
    return;
  }

  const same = findRecord(id);
  if (same) {
    input.classList.add("invalid");
    box.classList.add("error");
    const name = same.protected ? "" : same.pref;
    box.appendChild(document.createTextNode(
      `Diese Kennung ist bereits vergeben${name ? ` (\u201e${name}\u201c)` : ""}. Jede Kennung darf nur einmal vorkommen. `
    ));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "subtle";
    btn.textContent = "Vorhandenen Eintrag \u00f6ffnen";
    btn.addEventListener("click", () => jumpToConcept(id));
    box.appendChild(btn);
    return;
  }
  // Auch andere vorgemerkte neue Eintraege pruefen.
  for (const [k, d] of App.drafts.entries()) {
    if (k === App.currentKey || d.originalId) continue;
    if (d.data && d.data.id === id) {
      input.classList.add("invalid");
      box.classList.add("error");
      box.appendChild(document.createTextNode(
        `Diese Kennung wird bereits in einem anderen neuen, noch nicht gespeicherten Eintrag verwendet. `
      ));
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "subtle";
      btn.textContent = "Entwurf \u00f6ffnen";
      btn.addEventListener("click", () => openDraft(k));
      box.appendChild(btn);
      return;
    }
  }
  const similar = App.state.records.find((r) => r.id.toLowerCase() === id.toLowerCase());
  if (similar) {
    box.classList.add("warn");
    box.textContent =
      `Eine \u00e4hnliche Kennung existiert bereits: ex:${similar.id}. Gro\u00df- und Kleinschreibung gelten als Unterschied \u2014 ` +
      "bitte pr\u00fcfen, ob dasselbe Konzept schon angelegt ist.";
  }
}

function showEditorForm(rec, opts) {
  document.getElementById("editor-empty").style.display = "none";
  document.getElementById("editor-form").style.display = "block";
  document.getElementById("protected-notice").style.display = "none";
  document.getElementById("protected-raw-wrap").style.display = "none";
  document.getElementById("concept-form").classList.remove("protected-mode");

  document.getElementById("editor-title").textContent = opts.isNew ? "Neuer Eintrag" : (rec.pref || rec.id);
  document.getElementById("editor-subline").textContent = opts.isNew ? "" : `ex:${rec.id} \u00b7 ${rec.type}`;

  const idInput = document.getElementById("f-id");
  idInput.value = rec.id || "";
  idInput.readOnly = !opts.isNew;
  idInput.classList.toggle("readonly-id", !opts.isNew);

  document.getElementById("f-lang").value = rec.lang || "de";
  document.getElementById("f-type").value = rec.type || "org";
  document.getElementById("f-pref").value = rec.pref || "";
  document.getElementById("f-note").value = rec.note || "";
  document.getElementById("f-synonym").checked = !!rec.synonym;

  fillRowList("alt-list", rec.alts, "z. B. Abk\u00fcrzung oder andere Schreibweise");
  fillRowList("exact-list", rec.exact, "z. B. https://d-nb.info/gnd/\u2026");
  fillRowList("close-list", rec.close, "z. B. https://de.wikipedia.org/wiki/\u2026");
  fillRelated(rec.related);

  const idHelp = document.getElementById("id-help");
  idHelp.textContent = opts.isNew
    ? "Erlaubt: Buchstaben ohne Umlaute, Ziffern, . _ - (Anfang: Buchstabe oder _). Sp\u00e4ter nicht mehr \u00e4nderbar."
    : "";
  idInput.title = opts.isNew ? "" : "Gesperrt. \u00c4nderung nur \u00fcber \u201eKennung \u00e4ndern \u2026\u201c.";
  document.getElementById("btn-rename").hidden = !!opts.isNew;

  currentDeleteTargetId = opts.isNew ? null : rec.id;
  App.dirty = false;
  App.saveFailed = false;
  App.touchedFields.clear();
  App.currentKey = opts.key || (opts.isNew ? null : rec.id);
  updateIdCheck();
  updateFieldChecks(false);
  updateFileControls();
  renderPending();
  renderSaveHint();
  updateSaveStatus();
  scheduleSynonymCheck(true);
}

function selectRecord(id) {
  if (App.selectedId === id) return;
  stashCurrentForm();
  selectRecordSilently(id);
}

function selectRecordSilently(id) {
  App.selectedId = id;
  App.dirty = false;
  const rec = App.state && App.state.records.find((r) => r.id === id);
  if (!rec) {
    clearEditor();
    renderTree();
    return;
  }
  if (rec.protected) {
    App.currentKey = null;
    showProtectedEditor(rec);
  } else {
    // Liegt eine Vormerkung vor, steht im Formular der vorgemerkte Stand.
    const draft = App.drafts.get(id);
    showEditorForm(draft ? { ...rec, ...draft.data } : rec, { isNew: false, key: id });
  }
  renderTree();
}

// ---------------------------------------------------------------------
// Prüfungspanel (rechts)
// ---------------------------------------------------------------------

function renderFindings() {
  const list = document.getElementById("findings-list");
  list.innerHTML = "";
  const findings = (App.state && App.state.findings) || [];
  const errors = findings.filter((f) => f.level === "error").length;
  const warnings = findings.filter((f) => f.level === "warning").length;

  const dot = document.getElementById("traffic-dot");
  const text = document.getElementById("traffic-text");
  const hasFile = !!(App.state && App.state.path);
  dot.className = "dot" + (errors ? " error" : warnings ? " warn" : hasFile ? " ok" : "");
  text.textContent = hasFile ? `${errors} Fehler, ${warnings} ${warnings === 1 ? "Hinweis" : "Hinweise"}` : "Keine Datei geladen.";

  // Filter-Leiste aktualisieren (Alle / Fehler / Hinweise)
  const filterBar = document.getElementById("findings-filter");
  if (filterBar) {
    filterBar.hidden = !hasFile || findings.length === 0;
    const counts = { all: findings.length, error: errors, warning: warnings };
    const names = { all: "Alle", error: "Fehler", warning: "Hinweise" };
    filterBar.querySelectorAll(".filter-pill").forEach((btn) => {
      const f = btn.dataset.filter;
      btn.textContent = `${names[f]} (${counts[f]})`;
      btn.classList.toggle("active", App.findingFilter === f);
      btn.setAttribute("aria-pressed", App.findingFilter === f ? "true" : "false");
    });
  }

  const visibleFindings = findings.filter((f) => App.findingFilter === "all" || f.level === App.findingFilter);
  if (hasFile && findings.length > 0 && visibleFindings.length === 0) {
    const empty = document.createElement("div");
    empty.className = "findings-empty";
    empty.textContent = App.findingFilter === "error"
      ? "Keine Fehler vorhanden."
      : "Keine Hinweise vorhanden.";
    list.appendChild(empty);
  }

  for (const f of visibleFindings) {
    const div = document.createElement("div");
    if (f.concept_ids && f.concept_ids.length > 1) {
      // Befund betrifft mehrere Konzepte (z. B. Synonymliste): jede ID einzeln anklickbar.
      div.className = "finding " + f.level;
      const head = document.createElement("div");
      for (const id of f.concept_ids) {
        if (!findRecord(id)) continue;
        const link = document.createElement("button");
        link.type = "button";
        link.className = "fid-link";
        link.textContent = `ex:${id}`;
        link.title = `Eintrag \u201e${id}\u201c \u00f6ffnen`;
        link.addEventListener("click", () => jumpToConcept(id));
        head.appendChild(link);
      }
      div.appendChild(head);
      div.appendChild(document.createTextNode(f.message));
      list.appendChild(div);
      continue;
    }
    const record = f.concept_id ? findRecord(f.concept_id) : null;
    div.className = "finding " + f.level + (record ? " clickable" : "");
    const isProtectedNote = record && record.protected && /zum Schutz vor Informationsverlust/.test(f.message);
    div.innerHTML =
      (f.concept_id ? `<span class="fid">ex:${escapeHtml(f.concept_id)}</span><br>` : "") +
      escapeHtml(isProtectedNote ? protectedShort(record) : f.message) +
      (record ? `<div class="jump">\u2192 Zum Eintrag springen</div>` : "");
    if (record) {
      // Befund anklickbar machen: springt zum betroffenen Eintrag, damit
      // Fehler nicht erst im Baum gesucht werden muessen.
      div.tabIndex = 0;
      div.setAttribute("role", "button");
      div.title = `Eintrag \u201e${f.concept_id}\u201c zum Bearbeiten \u00f6ffnen`;
      const jump = () => jumpToConcept(f.concept_id);
      div.addEventListener("click", jump);
      div.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          jump();
        }
      });
    }
    list.appendChild(div);
  }
  renderSaveHint();
}

// Was verhindert das Speichern? Nach der Regel im Server: nur Fehler im gerade
// bearbeiteten Eintrag und Fehler, die die ganze Datei betreffen. Hinweise nie.
function renderSaveHint() {
  const el = document.getElementById("save-hint");
  if (!App.state || !App.state.path) {
    el.textContent = "";
    return;
  }
  const errors = ((App.state.findings) || []).filter((f) => f.level === "error");
  const warnings = ((App.state.findings) || []).length - errors.length;
  const sel = App.selectedId && App.selectedId !== "__NEW__" ? App.selectedId : null;
  const wholeFile = errors.filter((f) => !f.concept_id).length;
  const own = sel ? errors.filter((f) => f.concept_id === sel).length : 0;
  let text;
  if (wholeFile) {
    text = "Fehler, die die ganze Datei betreffen, verhindern das Speichern.";
  } else if (own) {
    text = "Fehler in diesem Eintrag verhindern das Speichern, bis sie behoben sind.";
  } else if (errors.length) {
    text = sel
      ? "Die vorhandenen Fehler betreffen andere Eintr\u00e4ge und verhindern das Speichern dieses Eintrags nicht."
      : "Beim Speichern z\u00e4hlen nur Fehler im gerade bearbeiteten Eintrag und Fehler, die die ganze Datei betreffen.";
  } else if (warnings) {
    text = "Hinweise verhindern das Speichern nicht.";
  } else {
    text = "Es liegen keine Befunde vor, die das Speichern verhindern.";
  }
  el.textContent = text;
}

function findRecord(id) {
  if (!App.state || !App.state.records) return null;
  return App.state.records.find((r) => r.id === id) || null;
}

function jumpToConcept(id) {
  const record = findRecord(id);
  if (!record) return;
  stashCurrentForm();
  // Suche/Filter zuruecksetzen, damit der gesuchte Eintrag im Baum auch
  // wirklich sichtbar ist und nicht durch einen aktiven Filter verdeckt wird.
  const search = document.getElementById("tree-search");
  const filter = document.getElementById("tree-type-filter");
  if (search.value || filter.value) {
    search.value = "";
    filter.value = "";
  }
  // Buchstabengruppe VOR selectRecordSilently aufklappen, damit renderTree nur einmal laeuft.
  const label = record.protected ? record.id : (record.pref || record.id);
  App.expandedLetters.add(groupLetterFor(label));
  selectRecordSilently(id);
  const node = document.querySelector(`[data-concept-id="${cssEscape(id)}"]`);
  if (node) node.scrollIntoView({ block: "center" });
  document.getElementById("editor-panel").scrollTop = 0;
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function updatePathBar() {
  const pathEl = document.getElementById("path-display");
  const path = (App.state && App.state.path) || "";
  pathEl.textContent = path || "Noch keine Datei ge\u00f6ffnet";
  pathEl.title = path;
  pathEl.classList.toggle("empty", !path);
  document.getElementById("concept-count").textContent =
    App.state && App.state.path ? `${App.state.records.length} Konzepte geladen` : "Keine Datei geladen";
}

function afterFileLoaded() {
  App.syncEnabled = false;
  App.persistDueAt = null;
  App.lastPersistTime = null;
  App.persistError = null;
  App.dirty = false;
  App.selectedId = null;
  App.drafts.clear();
  App.currentKey = null;
  App.failedId = null;
  App.findingFilter = "all";
  clearEditor();
  renderTree();
  renderFindings();
  updatePathBar();
  updateFileControls();
  App.justSaved = null;
  refreshBackupStatus();
  checkRecovery();
}

// ---------------------------------------------------------------------
// Aktionen: Öffnen / Durchsuchen / Prüfen
// ---------------------------------------------------------------------

async function validateWholeFile() {
  if (!requireFile("Datei pr\u00fcfen")) return;
  const previousSha = App.state.sha256;
  const previousSelected = App.selectedId;
  try {
    App.state = await apiPost("/api/validate", {});
    renderTree();
    renderFindings();
    updatePathBar();

    const changedExternally = !!(previousSha && App.state.sha256 !== previousSha);
    const { errors, warnings } = findingCounts(App.state);
    if (!changedExternally && errors === 0) {
      showBanner(
        warnings
          ? `Datei gepr\u00fcft: keine Fehler, ${warnings} ${warnings === 1 ? "Hinweis" : "Hinweise"} im Pr\u00fcfungspanel rechts.`
          : "Datei gepr\u00fcft: keine Fehler und keine Hinweise.",
        warnings ? "warn" : "ok"
      );
      return;
    }

    let body = describeState(App.state);
    if (changedExternally) {
      body +=
        "\n\nHinweis: Die Datei wurde seit dem letzten Einlesen au\u00dferhalb des Editors " +
        "ver\u00e4ndert und ist jetzt neu eingelesen.";
      if (pendingCount()) {
        body += " Noch nicht gespeicherte \u00c4nderungen stammen vom \u00e4lteren Stand.";
      }
      if (previousSelected && previousSelected !== "__NEW__" && !findRecord(previousSelected)) {
        body += ` Der ausgew\u00e4hlte Eintrag \u201e${previousSelected}\u201c existiert im neuen Stand nicht mehr.`;
      }
    }
    const kind = stateKind(App.state);
    showModal("Datei gepr\u00fcft", body, kind);
  } catch (err) {
    handleApiError(err, "Pr\u00fcfung fehlgeschlagen");
  }
}

// Datei oeffnen ueber das Windows-Auswahlfenster. Der Server oeffnet es und
// antwortet sofort; das Ergebnis wird hier abgefragt. Solange das Fenster
// offen ist, verdeckt ein Hinweisdialog die Seite: kein Mehrfachklick, und es
// ist klar, wo es weitergeht (das Fenster kann hinter dem Browser liegen).
let choosePolling = false;

function showChooseWaitingModal() {
  showModal(
    "Dateiauswahl ge\u00f6ffnet",
    "Es wurde ein Fenster \u201eTTL-Datei \u00f6ffnen\u201c ge\u00f6ffnet. Bitte dort die .ttl-Datei " +
      "ausw\u00e4hlen und auf \u201e\u00d6ffnen\u201c klicken \u2013 oder auf \u201eAbbrechen\u201c.\n\n" +
      "Sie sehen das Fenster nicht? Dann liegt es vermutlich hinter dem Browser. " +
      "Klicken Sie auf \u201eFenster nach vorne holen\u201c oder unten in der Taskleiste " +
      "auf das Symbol \u201eFPV-Editor\u201c.",
    "progress",
    { noClose: true }
  );
  const extra = document.getElementById("modal-extra");
  const row = document.createElement("div");
  row.className = "choice-row";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "Fenster nach vorne holen";
  btn.addEventListener("click", async () => {
    try {
      await apiPost("/api/choose", {});
    } catch (err) {
      handleApiError(err, "Datei \u00f6ffnen");
    }
  });
  row.appendChild(btn);
  extra.appendChild(row);
  btn.focus();
}

async function pollChooseResult() {
  if (choosePolling) return;
  choosePolling = true;
  try {
    for (;;) {
      if (serverGone) return;
      await new Promise((r) => setTimeout(r, 500));
      const resp = await apiPost("/api/choose-result", {});
      if (resp.status === "open") continue;
      if (resp.status === "loaded") {
        hideModal();
        App.state = resp;
        afterFileLoaded();
        const { errors, warnings } = findingCounts(App.state);
        const summary = errors || warnings
          ? `${errors} Fehler, ${warnings} ${warnings === 1 ? "Hinweis" : "Hinweise"} (Details rechts)`
          : "keine Befunde";
        showBanner(
          `Datei ge\u00f6ffnet: ${fileBaseName(App.state.path)} \u2014 ${App.state.records.length} Konzepte (${summary}).`,
          errors ? "warn" : warnings ? "info" : "ok",
          { durationMs: errors ? 10000 : 7000 }
        );
      } else if (resp.status === "cancelled") {
        hideModal();
        showNothingDone("Datei \u00f6ffnen", "Es wurde keine Datei ausgew\u00e4hlt; die bisherige Datei bleibt ge\u00f6ffnet.");
      } else {
        // "idle": Ergebnis wurde bereits von einem anderen Browser-Tab abgeholt.
        hideModal();
      }
      return;
    }
  } catch (err) {
    if (!serverGone) handleApiError(err, "Datei \u00f6ffnen fehlgeschlagen");
  } finally {
    choosePolling = false;
  }
}

async function openFile() {
  if (choosePolling) {
    showChooseWaitingModal();
    return;
  }
  if (!(await confirmDiscardIfDirty("open"))) {
    showNothingDone("Datei \u00f6ffnen", "Abgebrochen; die nicht gespeicherten \u00c4nderungen bleiben erhalten.");
    return;
  }
  if (pendingCount()) await discardPendingOnServer();
  try {
    // Antwort "opened" oder "already_open" \u2013 in beiden F\u00e4llen warten.
    await apiPost("/api/choose", {});
  } catch (err) {
    handleApiError(err, "Datei \u00f6ffnen fehlgeschlagen");
    return;
  }
  showChooseWaitingModal();
  pollChooseResult();
}

// ---------------------------------------------------------------------
// Verbindung zum Programm
// ---------------------------------------------------------------------
// Alle paar Sekunden ein Lebenszeichen abfragen. Bleibt die Antwort zweimal
// aus, wurde das Programm beendet (z. B. ueber das kleine Startfenster):
// Die Seite wird dann deutlich als beendet markiert, statt weiter aktiv
// auszusehen.
const PING_MS = 4000;
let pingFailures = 0;
let serverGone = false;

async function pingServer() {
  if (serverGone) return true;
  try {
    await fetch("/api/ping", { cache: "no-store" });
    pingFailures = 0; // jede HTTP-Antwort heisst: Programm laeuft
    return true;
  } catch {
    pingFailures += 1;
    if (pingFailures >= 2) showServerGone();
    return false;
  }
}

// Nach einem Verbindungsfehler sofort pruefen, statt auf den Takt zu warten.
async function checkServerAlive() {
  if (serverGone) return;
  if (!(await pingServer()) && !serverGone) setTimeout(pingServer, 600);
}

function showServerGone(text) {
  serverGone = true;
  hideModal();
  if (text) document.getElementById("offline-text").textContent = text;
  document.getElementById("offline-overlay").classList.remove("hidden");
}

async function doCloseFile() {
  if (!requireFile("Datei schlie\u00dfen")) return;
  if (!(await confirmDiscardIfDirty("close"))) {
    showNothingDone("Datei schlie\u00dfen", "Abgebrochen; die Datei bleibt ge\u00f6ffnet.");
    return;
  }
  if (pendingCount()) await discardPendingOnServer();
  const previous = App.state.path;
  try {
    const resp = await apiPost("/api/close", {});
    App.state = resp;
    // Suche und Filter mit zuruecksetzen, damit beim naechsten Oeffnen
    // nicht unbemerkt noch ein Filter der vorherigen Datei aktiv ist.
    document.getElementById("tree-search").value = "";
    document.getElementById("tree-type-filter").value = "";
    App.expandedLetters.clear();
    afterFileLoaded();
    showBanner(
      `Datei geschlossen (${fileBaseName(previous)}). Es wurde nichts ver\u00e4ndert; ein manuell gew\u00e4hlter Sicherungsort wurde zur\u00fcckgesetzt.`,
      "ok"
    );
  } catch (err) {
    handleApiError(err, "Schlie\u00dfen fehlgeschlagen");
  }
}

async function doStorageCheck() {
  if (!requireFile("Schreibzugriff pr\u00fcfen")) return;
  showModal("Schreibzugriff pr\u00fcfen \u2026", "Sicherungsort und Dateiordner werden getestet.", "progress");
  try {
    const resp = await apiPost("/api/storage-check", {});
    const lines = resp.results
      .map(
        (r) =>
          `${r.writable ? "\u2713" : "\u2717"} ${r.location}\n   ${r.path}` +
          (r.replace_tested ? " (Ersatztest ok)" : "") +
          (r.error ? `\n   Fehler: ${r.error}` : "")
      )
      .join("\n\n");
    showModal(
      "Schreibzugriff gepr\u00fcft",
      lines +
        "\n\nHinweis: Dies belegt nur, dass der Ordner beschreibbar ist \u2014 nicht automatisch, " +
        "dass die vorhandene TTL selbst ge\u00f6ffnet oder ersetzt werden darf.",
      "ok"
    );
  } catch (err) {
    handleApiError(err, "Pr\u00fcfung fehlgeschlagen");
  }
}

async function doOpenBackups() {
  if (!requireFile("Sicherungen anzeigen")) return;
  try {
    const resp = await apiGet("/api/backups");
    showBackupsModal(resp.backups || []);
  } catch (err) {
    handleApiError(err, "Sicherungen konnten nicht geladen werden");
  }
}

// ---------------------------------------------------------------------
// Kennung aendern (bewusste Sonderaktion)
// ---------------------------------------------------------------------

async function startRename() {
  if (!requireFile("Kennung \u00e4ndern")) return;
  const id = App.selectedId && App.selectedId !== "__NEW__" ? App.selectedId : null;
  if (!id) {
    showNothingDone("Kennung \u00e4ndern", "Es ist kein bestehender Eintrag ausgew\u00e4hlt.");
    return;
  }
  if (pendingCount()) {
    showNothingDone(
      "Kennung \u00e4ndern",
      "Es gibt noch nicht gespeicherte \u00c4nderungen. Bitte zuerst alle speichern oder verwerfen: " +
        "Beim \u00c4ndern einer Kennung werden auch Verweise in anderen Eintr\u00e4gen angepasst, " +
        "und vorgemerkte \u00c4nderungen w\u00fcrden diese Anpassung sonst \u00fcberschreiben."
    );
    return;
  }
  let info;
  try {
    info = await apiPost("/api/rename-check", { id });
  } catch (err) {
    handleApiError(err, "Kennung \u00e4ndern nicht m\u00f6glich");
    return;
  }
  showRenameModal(id, info);
}

const ID_RE = /^[A-Za-z_][A-Za-z0-9._-]*$/;

function showRenameModal(oldId, info) {
  const overlay = document.getElementById("modal-overlay");
  document.getElementById("modal-box").className = "modal state-info";
  document.getElementById("modal-title").textContent = "Kennung \u00e4ndern";
  const closeBtn = document.getElementById("modal-close");
  closeBtn.textContent = "Abbrechen";

  const body = document.getElementById("modal-body");
  const extra = document.getElementById("modal-extra");
  extra.innerHTML = "";

  const lines = [`Bisherige Kennung: ex:${oldId}`, `Adresse: ${info.uri}`];
  if (info.blocked && info.blocked.length) {
    lines.push(
      "",
      "Das \u00c4ndern ist derzeit nicht m\u00f6glich: Auf diesen Eintrag verweisen Eintr\u00e4ge, die der Editor nicht ver\u00e4ndert:"
    );
    info.blocked.forEach((b) => lines.push(`\u2022 ex:${b.id} \u2014 ${b.reason}`));
    lines.push("", "Bitte diese Verweise zuerst im Texteditor anpassen (oder die Eintr\u00e4ge dort umbenennen) und die Datei neu \u00f6ffnen.");
    body.textContent = lines.join("\n");
    overlay.classList.remove("hidden");
    closeBtn.textContent = "Schlie\u00dfen";
    closeBtn.focus();
    return;
  }
  lines.push("");
  if (info.referrers.length) {
    lines.push(`Diese ${info.referrers.length} Konzept(e) verweisen auf den Eintrag und werden automatisch angepasst:`);
    info.referrers.forEach((r) => lines.push(`\u2022 ex:${r.id}${r.pref ? " \u2014 " + r.pref : ""}`));
  } else {
    lines.push("Kein anderes Konzept in dieser Datei verweist auf diesen Eintrag.");
  }
  body.textContent = lines.join("\n");

  const warn = document.createElement("div");
  warn.className = "rename-warn";
  warn.textContent =
    "Wichtig: Die Kennung ist Teil der Adresse des Konzepts. Verwendungen au\u00dferhalb dieser Datei " +
    "(z. B. in den Editions-XML oder im Typesense-Index) kann der Editor weder finden noch \u00e4ndern; " +
    "sie m\u00fcssen von Hand angepasst werden. Vor dem Schreiben wird eine gepr\u00fcfte Sicherung angelegt.";

  const form = document.createElement("div");
  form.className = "rename-form";
  const label = document.createElement("label");
  label.textContent = "Neue Kennung";
  label.htmlFor = "rename-new-id";
  const input = document.createElement("input");
  input.type = "text";
  input.id = "rename-new-id";
  input.className = "mono";
  input.autocomplete = "off";
  const msg = document.createElement("p");
  msg.className = "id-check";
  msg.setAttribute("role", "status");
  const checkLine = document.createElement("label");
  checkLine.className = "check-line";
  const check = document.createElement("input");
  check.type = "checkbox";
  const checkText = document.createElement("span");
  checkText.textContent = "Ich habe verstanden, dass Verwendungen au\u00dferhalb dieser Datei nicht angepasst werden.";
  checkLine.appendChild(check);
  checkLine.appendChild(checkText);

  const okBtn = document.createElement("button");
  okBtn.type = "button";
  okBtn.textContent = "Kennung \u00e4ndern";
  okBtn.disabled = true;

  function validate() {
    const v = input.value.trim();
    msg.textContent = "";
    msg.className = "id-check";
    input.classList.remove("invalid");
    let ok = false;
    if (v) {
      if (!ID_RE.test(v)) {
        msg.className = "id-check error";
        msg.textContent = "Erlaubt: Buchstaben ohne Umlaute, Ziffern, . _ - (Anfang: Buchstabe oder _).";
      } else if (v === oldId) {
        msg.className = "id-check error";
        msg.textContent = "Das ist die bisherige Kennung.";
      } else if (findRecord(v)) {
        msg.className = "id-check error";
        msg.textContent = `Die Kennung \u201e${v}\u201c ist bereits vergeben.`;
      } else {
        ok = true;
        const similar = App.state.records.find((r) => r.id.toLowerCase() === v.toLowerCase());
        if (similar) {
          msg.className = "id-check warn";
          msg.textContent = `Eine \u00e4hnliche Kennung existiert bereits: ex:${similar.id} (Gro\u00df-/Kleinschreibung z\u00e4hlt als Unterschied).`;
        }
      }
      if (msg.classList.contains("error")) input.classList.add("invalid");
    }
    okBtn.disabled = !(ok && check.checked);
  }
  input.addEventListener("input", validate);
  check.addEventListener("change", validate);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !okBtn.disabled) doRename(oldId, input.value.trim());
  });
  okBtn.addEventListener("click", () => doRename(oldId, input.value.trim()));

  form.appendChild(label);
  form.appendChild(input);
  form.appendChild(msg);
  form.appendChild(checkLine);
  form.appendChild(okBtn);
  extra.appendChild(warn);
  extra.appendChild(form);
  overlay.classList.remove("hidden");
  input.focus();
}

async function doRename(oldId, newId) {
  showModal(
    "Kennung wird ge\u00e4ndert \u2026",
    "Sicherung wird angelegt, dann werden Eintrag und Verweise angepasst.",
    "progress"
  );
  try {
    const resp = await apiPost("/api/rename", { id: oldId, new_id: newId, version: App.state.sha256 });
    App.state = resp;
    App.dirty = false;
    App.saveFailed = false;
    App.justSaved = {
      ids: [newId],
      time: new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }),
      atomic: resp.write_method === "atomic",
    };
    renderTree();
    renderFindings();
    updatePathBar();
    selectRecordSilently(newId);
    refreshBackupStatus();
    const updated = (resp.renamed && resp.renamed.updated_references) || [];
    const methodText = resp.write_method === "atomic" ? "atomar (os.replace)" : "direkter R\u00fcckfall (r+b)";
    const msg =
      `ex:${oldId}  \u2192  ex:${newId}\n\n` +
      (updated.length
        ? `Verweise wurden automatisch angepasst in ${updated.length} Konzept(en): ${updated.map((i) => "ex:" + i).join(", ")}\n\n`
        : "Kein anderes Konzept in dieser Datei verwies auf den Eintrag.\n\n") +
      "Der vorherige Stand wurde automatisch gesichert (wiederherstellbar \u00fcber \u201eFr\u00fchere St\u00e4nde \u2026\u201c).\n\n" +
      "Bitte beachten: Verwendungen der alten Kennung au\u00dferhalb dieser Datei (z. B. Editions-XML, Typesense-Index) " +
      "m\u00fcssen von Hand angepasst werden.";
    showModal("Kennung ge\u00e4ndert", msg, "ok");
    appendTechDetails([
      `Sicherung: ${resp.backup_path}`,
      `Schreibmethode: ${methodText}`,
    ]);
  } catch (err) {
    handleApiError(err, "Kennung \u00e4ndern fehlgeschlagen");
  }
}

const HELP_TEXT =
  "\u00c4nderungen sammeln und speichern\n" +
  "Sie k\u00f6nnen nacheinander mehrere Eintr\u00e4ge \u00e4ndern oder neu anlegen. Beim Wechsel zu einem anderen Eintrag wird die \u00c4nderung vorgemerkt " +
  "(\u25cf in der Liste links, gelbe Schaltfl\u00e4chen oben im Formular) und noch nicht in die Datei geschrieben. " +
  "\u201eAlle \u00c4nderungen speichern\u201c pr\u00fcft alles gemeinsam und schreibt es in einem Schritt. Fehlt etwas oder ist ein Eintrag fehlerhaft, " +
  "wird gar nichts geschrieben und die Meldung nennt den Eintrag. \u201eDiesen Eintrag zur\u00fccksetzen\u201c nimmt nur die \u00c4nderungen am ge\u00f6ffneten Eintrag zur\u00fcck, \u201eAlle verwerfen\u201c alle vorgemerkten.\n\n" +
  "Beenden und Zwischensicherung\n" +
  "Beim Beenden mit nicht gespeicherten Eintr\u00e4gen fragt der Editor (auch das kleine Startfenster), ob gespeichert werden soll; sonst fragt er, ob wirklich beendet werden soll. " +
  "Ist das Programm beendet, zeigt die Browserseite das deutlich an; sie kann dann geschlossen werden. " +
  "Zus\u00e4tzlich wird alle 10 Minuten eine Zwischensicherung der vorgemerkten Eintr\u00e4ge angelegt (%LOCALAPPDATA%\\FPV-Editor\\recovery). " +
  "Sie ersetzt das Speichern nicht und \u00e4ndert die TTL-Datei nicht. Nach einem Absturz bietet der Editor beim n\u00e4chsten \u00d6ffnen der Datei an, die Eintr\u00e4ge wiederherzustellen.\n\n" +
  "Datei \u00f6ffnen\n" +
  "\u201eDatei \u00f6ffnen \u2026\u201c zeigt das Windows-Fenster zur Dateiauswahl. Solange es offen ist, steht im Browser ein Hinweis. " +
  "Ist das Fenster nicht zu sehen, liegt es hinter dem Browser: \u201eFenster nach vorne holen\u201c anklicken oder in der Taskleiste auf \u201eFPV-Editor\u201c klicken.\n\n" +
  "Fr\u00fchere St\u00e4nde (lokales Sicherheitsnetz)\n" +
  "Vor jedem Speichern legt der Editor still eine lokale Sicherung des vorherigen Stands an (die letzten 15 St\u00e4nde bleiben unter %LOCALAPPDATA%\\FPV-Editor\\backups erhalten, \u00e4ltere werden automatisch aufger\u00e4umt; langfristige Historie liegt in Git). " +
  "\u00dcber \u201eFr\u00fchere St\u00e4nde \u2026\u201c l\u00e4sst sich ein Stand von vor dem letzten Commit jederzeit zur\u00fcckholen.\n\n" +
  "Was das Speichern verhindert\n" +
  "Nur Fehler in den Eintr\u00e4gen, die Sie gerade speichern, und Fehler, die die ganze Datei betreffen (z. B. ung\u00fcltiges Turtle). " +
  "Hinweise und Fehler in anderen Eintr\u00e4gen verhindern das Speichern nicht.\n\n" +
  "Gesch\u00fctzte Eintr\u00e4ge (\ud83d\udd12 in der Liste links)\n" +
  "Eintr\u00e4ge mit unbekannten Feldern, Kommentaren, mehrzeiligen Texten in dreifachen Anf\u00fchrungszeichen, mehreren bevorzugten Benennungen " +
  "oder mehreren Typangaben werden nicht im Formular bearbeitet, damit beim Speichern nichts verloren geht. " +
  "Sie lassen sich in einem Texteditor bearbeiten; danach die Datei neu \u00f6ffnen. " +
  "L\u00f6schen bleibt m\u00f6glich, wenn kein anderer Eintrag darauf verweist.\n\n" +
  "Synonymliste (Typesense)\n" +
  "Konzepte mit dem Haken \u201eIn Synonymliste verwenden\u201c gehen mit allen ihren Benennungen in die Synonymliste der Suche. " +
  "Steht dieselbe Benennung (z. B. eine Abk\u00fcrzung) bei zwei solchen Konzepten, w\u00fcrde die Suche danach beide finden. " +
  "Der Editor verhindert das beim Speichern; Gro\u00df-/Kleinschreibung z\u00e4hlt dabei nicht als Unterschied. " +
  "Kollisionen, die schon in der Datei stehen, erscheinen als Hinweis und blockieren nicht. " +
  "Ein Konzept bekommt erst ab zwei verwertbaren Benennungen ein Synonymset (Kurzcodes wie org, pol und Einzelbuchstaben z\u00e4hlen nicht).\n\n" +
  "Kennungen\n" +
  "Die Kennung (ID) ist Teil der Adresse (URI) des Konzepts und deshalb im Formular gesperrt. \u00c4ndern l\u00e4sst sie sich nur bewusst \u00fcber \u201eKennung \u00e4ndern \u2026\u201c unter dem Feld: " +
  "Verweise in anderen Eintr\u00e4gen werden dabei automatisch angepasst. Verwendungen au\u00dferhalb der Datei (Edition, Typesense) nicht; die m\u00fcssen von Hand ge\u00e4ndert werden.\n\n" +
  "Technische Namen & Tastenk\u00fcrzel\n" +
  "Grau neben den Feldbezeichnungen stehen die Feldnamen der Datei (z. B. skos:prefLabel). Sie helfen bei der Fehlersuche im Quelltext. " +
  "Mit Strg+S k\u00f6nnen Sie alle vorgemerkten \u00c4nderungen direkt speichern. Kurzbeschreibungen (skos:note) sind einzeilig \u2014 Enter wird automatisch zu einem Leerzeichen. " +
  "Unkritische Hinweise erscheinen oben im Statusbanner, Fehler und Sicherheitsabfragen immer als eigenes Dialogfenster.";

function showHelp() {
  showModal("Hilfe", HELP_TEXT, "info");
  document.getElementById("modal-close").textContent = "Schlie\u00dfen";
}

function doChooseBackupDir() {
  showPromptModal(
    "Sicherungsort w\u00e4hlen",
    "Vollst\u00e4ndigen Ordnerpfad aus der Explorer-Adresszeile hier einf\u00fcgen. Der Ordner muss " +
      "bereits existieren und beschreibbar sein. Diese Wahl gilt nur f\u00fcr die laufende Sitzung.",
    async (value) => {
      try {
        const resp = await apiPost("/api/backup-directory", { path: value });
        refreshBackupStatus();
        showBanner(`Sicherungsort f\u00fcr diese Sitzung \u00fcbernommen: ${resp.path}`, "ok");
      } catch (err) {
        handleApiError(err, "Sicherungsort ung\u00fcltig");
      }
    }
  );
}

async function doQuit() {
  const n = pendingCount();
  if (n) {
    showQuitChoice(n);
    return;
  }
  const confirmed = await showConfirmModal(
    "FPV-Editor beenden?",
    "Den FPV-Editor wirklich beenden?\n\nDanach funktioniert die Seite im Browser nicht mehr; das Browserfenster kann anschlie\u00dfend geschlossen werden.",
    {
      confirmLabel: "Programm beenden",
      cancelLabel: "Weiterarbeiten",
      danger: true,
      kind: "warn",
    }
  );
  if (!confirmed) {
    showNothingDone("App beenden", "Abgebrochen; die App l\u00e4uft weiter.");
    return;
  }
  await quitNow(false);
}

// Es gibt nicht gespeicherte Eintraege: speichern und beenden, ohne Speichern
// beenden oder zurueck zum Editor.
function showQuitChoice(n) {
  stashCurrentForm();
  const names = [...App.drafts.values()].slice(0, 8).map((d) => "\u2022 " + draftLabel(d));
  if (App.drafts.size > 8) names.push(`\u2026 und ${App.drafts.size - 8} weitere`);
  showChoiceModal(
    "Nicht gespeicherte \u00c4nderungen",
    `${n === 1 ? "1 Eintrag ist" : n + " Eintr\u00e4ge sind"} noch nicht gespeichert:\n\n${names.join("\n")}\n\nWas soll geschehen?`,
    "warn",
    [
      { label: "Speichern und beenden", onClick: () => saveAll({ thenQuit: true }) },
      { label: "Beenden ohne Speichern", className: "danger", onClick: () => quitNow(true) },
    ],
    "Zur\u00fcck zum Editor"
  );
}

async function quitNow(discard) {
  try {
    await apiPost("/api/quit", { force: true, discard: !!discard });
    showServerGone(
      (discard ? "Die nicht gespeicherten \u00c4nderungen wurden verworfen. " : "") +
        "Das Programm wurde auf Ihren Wunsch beendet."
    );
  } catch (err) {
    handleApiError(err, "Beenden fehlgeschlagen");
  }
}

function startNewEntry() {
  if (!requireFile("Neuer Eintrag")) return;
  stashCurrentForm();
  App.selectedId = "__NEW__";
  showEditorForm(
    { id: "", lang: "de", type: "org", pref: "", note: "", synonym: false, alts: [], exact: [], close: [], related: [] },
    { isNew: true }
  );
  renderTree();
}

// ---------------------------------------------------------------------
// Speichern / Löschen
// ---------------------------------------------------------------------

// Das Formular wird nie nativ abgeschickt (kein Submit-Button; Enter in einem
// Textfeld darf nicht versehentlich speichern). Speichern nur ueber den Button.
function onFormSubmit(e) {
  e.preventDefault();
}

async function saveAll(opts) {
  const thenQuit = !!(opts && opts.thenQuit);
  if (!requireFile("\u00c4nderungen speichern")) return;
  const current = App.selectedId && App.selectedId !== "__NEW__" ? findRecord(App.selectedId) : null;
  if (current && current.protected && !App.drafts.size) {
    showNothingDone(
      "\u00c4nderungen speichern",
      `Der Eintrag \u201e${current.id}\u201c ist gesch\u00fctzt und wird nicht \u00fcber das Formular gespeichert. Es wurde nichts ge\u00e4ndert.`
    );
    return;
  }
  stashCurrentForm();
  if (!App.drafts.size) {
    showNothingDone(
      "\u00c4nderungen speichern",
      App.selectedId
        ? "Es wurde nichts ge\u00e4ndert; die Datei bleibt unver\u00e4ndert."
        : "Es gibt keine \u00c4nderungen zu speichern. \u00c4ndern Sie links einen Eintrag oder legen Sie \u00fcber \u201e\uff0b Neuer Eintrag\u201c einen neuen an."
    );
    return;
  }
  // Neue Eintraege mit bereits vergebener Kennung fruehzeitig melden.
  for (const d of App.drafts.values()) {
    if (!d.originalId && d.data.id && findRecord(d.data.id)) {
      showNothingDone(
        "\u00c4nderungen speichern",
        `Die Kennung \u201e${d.data.id}\u201c ist bereits vergeben; jede Kennung darf nur einmal vorkommen. Es wurde nichts gespeichert.`
      );
      return;
    }
  }

  const drafts = [...App.drafts.values()];
  const shownKey = App.currentKey;
  const shownDraft = shownKey ? App.drafts.get(shownKey) : null;
  const items = drafts.map((d) => ({ original_id: d.originalId, data: d.data }));

  showModal(
    "Speichern \u2026",
    `${items.length} ${items.length === 1 ? "Eintrag" : "Eintr\u00e4ge"}: Sicherung wird angelegt, dann wird die Datei geschrieben.`,
    "progress"
  );
  try {
    const resp = await apiPost("/api/save-batch", { version: App.state.sha256, items });
    App.state = resp;
    App.dirty = false;
    App.saveFailed = false;
    App.failedId = null;
    App.drafts.clear();
    const savedIds = resp.saved_ids || items.map((i) => i.data.id);
    App.justSaved = {
      ids: savedIds,
      time: new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }),
      atomic: resp.write_method === "atomic",
    };
    renderTree();
    renderFindings();
    updatePathBar();
    const showId = shownDraft ? shownDraft.data.id : App.selectedId;
    if (showId && findRecord(showId)) selectRecordSilently(showId);
    else clearEditor();
    renderPending();
    refreshBackupStatus();

    const methodText =
      resp.write_method === "atomic"
        ? "atomar (os.replace)"
        : "direkter R\u00fcckfall (r+b)";
    const singleRec = items.length === 1 ? findRecord(savedIds[0]) : null;
    const singleLabel = singleRec && !singleRec.protected && singleRec.pref
      ? `\u201e${singleRec.pref}\u201c (ex:${savedIds[0]})`
      : `\u201e${savedIds[0]}\u201c`;
    const otherErrors = (resp.findings || []).filter((f) => f.level === "error" && !savedIds.includes(f.concept_id));
    const techLines = [
      `Sicherung: ${resp.backup_path}`,
      `Schreibmethode: ${methodText}`,
    ];

    if (thenQuit) {
      await apiPost("/api/quit", { force: true });
      const msg =
        (items.length === 1
          ? `Der Eintrag ${singleLabel} wurde gespeichert.`
          : `${items.length} Eintr\u00e4ge wurden gespeichert:\n${savedIds.map((i) => "\u2022 ex:" + i).join("\n")}`) +
        "\n\nDie Anwendung wird jetzt beendet. Dieses Browserfenster kann geschlossen werden.";
      showModal("Gespeichert \u2014 Programm wird beendet", msg, "ok");
      appendTechDetails(techLines);
      return;
    }

    if (resp.write_method !== "atomic") {
      let msg =
        (items.length === 1
          ? `Der Eintrag ${singleLabel} wurde gespeichert.`
          : `${items.length} Eintr\u00e4ge wurden gespeichert:\n${savedIds.map((i) => "\u2022 ex:" + i).join("\n")}`) +
        "\n\nHinweis: Die Datei musste direkt \u00fcberschrieben werden. Sollte dabei ein Problem aufgetreten sein, " +
        "l\u00e4sst sich der vorherige Stand \u00fcber \u201eFr\u00fchere St\u00e4nde \u2026\u201c zur\u00fcckholen.";
      if (otherErrors.length) {
        msg += `\n\nAu\u00dferdem gibt es in ${otherErrors.length} anderen Eintr\u00e4gen noch Fehler (siehe Pr\u00fcfungspanel rechts).`;
      }
      showModal("Gespeichert (mit Hinweis)", msg, "warn");
      appendTechDetails(techLines);
      return;
    }

    // Regelfall (atomar gespeichert): kein blockierendes Modal, sondern klares
    // gruenes Status-Banner oben + Zeitstempel neben dem Speichern-Knopf.
    hideModal();
    let banner = items.length === 1
      ? `Gespeichert: ${singleLabel}.`
      : `Gespeichert: ${items.length} Eintr\u00e4ge (${savedIds.slice(0, 5).map((i) => "ex:" + i).join(", ")}${savedIds.length > 5 ? " \u2026" : ""}).`;
    if (otherErrors.length) {
      banner += ` Hinweis: ${otherErrors.length} Fehler in anderen Eintr\u00e4gen (siehe rechts).`;
    }
    showBanner(banner, "ok", { durationMs: 8000 });
  } catch (err) {
    App.saveFailed = true;
    App.failedId = err.failedId || null;
    updateFieldChecks(true);
    updateIdCheck();
    updateSaveStatus();
    renderPending();
    handleApiError(
      err,
      thenQuit
        ? "Speichern fehlgeschlagen \u2014 das Programm wurde NICHT beendet, es wurde nichts geschrieben"
        : "Speichern fehlgeschlagen \u2014 es wurde nichts geschrieben"
    );
  }
}

// Setzt NUR den gerade geoeffneten Eintrag auf den gespeicherten Stand zurueck.
async function discardCurrent() {
  if (!requireFile("Eintrag zur\u00fccksetzen")) return;
  if (!App.selectedId) {
    showNothingDone("Eintrag zur\u00fccksetzen", "Es ist kein Eintrag ge\u00f6ffnet.");
    return;
  }
  const key = App.currentKey;
  const hasChange = App.dirty || (key && App.drafts.has(key));
  if (!hasChange) {
    showNothingDone(
      "Eintrag zur\u00fccksetzen",
      "Der ge\u00f6ffnete Eintrag ist unver\u00e4ndert." +
        (pendingCount() ? " Andere Eintr\u00e4ge sind noch vorgemerkt; \u00f6ffnen Sie einen davon oder verwerfen Sie alle mit \u201eAlle verwerfen\u201c." : "")
    );
    return;
  }
  const isNew = App.selectedId === "__NEW__";
  const confirmed = await showConfirmModal(
    isNew ? "Neuen Eintrag verwerfen?" : "\u00c4nderungen an diesem Eintrag verwerfen?",
    isNew
      ? "Den neuen, noch nicht gespeicherten Eintrag wirklich verwerfen?"
      : `Die nicht gespeicherten \u00c4nderungen am Eintrag \u201e${App.selectedId}\u201c wirklich verwerfen? Andere vorgemerkte Eintr\u00e4ge bleiben erhalten.`,
    {
      confirmLabel: isNew ? "Neuen Eintrag verwerfen" : "\u00c4nderungen verwerfen",
      cancelLabel: "Abbrechen",
      danger: true,
    }
  );
  if (!confirmed) {
    showNothingDone("Eintrag zur\u00fccksetzen", "Abgebrochen; die \u00c4nderungen bleiben erhalten.");
    return;
  }
  if (key) App.drafts.delete(key);
  App.dirty = false;
  const id = App.selectedId;
  if (isNew) clearEditor();
  else selectRecordSilently(id);
  renderPending();
  renderTree();
  showBanner(
    isNew ? "Der neue Eintrag wurde verworfen." : `Der Eintrag \u201e${id}\u201c steht wieder auf dem gespeicherten Stand.`,
    "ok"
  );
}

async function onDeleteClick() {
  if (!requireFile("Eintrag l\u00f6schen")) return;
  const id = currentDeleteTargetId || (App.selectedId !== "__NEW__" ? App.selectedId : null);
  if (!id) {
    showNothingDone(
      "Eintrag l\u00f6schen",
      App.selectedId === "__NEW__"
        ? "Der neue Eintrag ist noch nicht gespeichert, es gibt daher nichts zu l\u00f6schen."
        : "Es ist kein Eintrag ausgew\u00e4hlt."
    );
    return;
  }
  const others = [...pendingKeys()].filter((k) => k !== id);
  if (others.length) {
    showNothingDone(
      "Eintrag l\u00f6schen",
      "Es gibt noch nicht gespeicherte \u00c4nderungen an anderen Eintr\u00e4gen. Bitte zuerst alle speichern oder verwerfen, " +
        "damit das L\u00f6schen nicht mit diesen \u00c4nderungen kollidiert."
    );
    return;
  }
  const rec = findRecord(id);
  const displayName = rec && !rec.protected && rec.pref ? `\u201e${rec.pref}\u201c (ex:${id})` : `ex:${id}`;
  const confirmed = await showConfirmModal(
    "Eintrag endg\u00fcltig l\u00f6schen?",
    `Eintrag ${displayName} wirklich aus der Datei l\u00f6schen?\n\nVor dem L\u00f6schen wird automatisch eine gepr\u00fcfte Sicherung angelegt. Das L\u00f6schen kann nur \u00fcber diese Sicherung r\u00fcckg\u00e4ngig gemacht werden.`,
    {
      confirmLabel: "Eintrag endg\u00fcltig l\u00f6schen",
      cancelLabel: "Abbrechen",
      danger: true,
      kind: "error",
    }
  );
  if (!confirmed) {
    showNothingDone("Eintrag l\u00f6schen", `Abgebrochen; der Eintrag \u201e${id}\u201c wurde nicht gel\u00f6scht.`);
    return;
  }
  showModal("L\u00f6schen \u2026", `Eintrag \u201e${id}\u201c wird gel\u00f6scht. Zuerst wird eine Sicherung angelegt.`, "progress");
  try {
    const resp = await apiPost("/api/delete", { id, version: App.state.sha256 });
    App.state = resp;
    App.dirty = false;
    App.drafts.delete(id);
    clearEditor();
    renderTree();
    renderFindings();
    updatePathBar();
    refreshBackupStatus();
    const methodText = resp.write_method === "atomic" ? "atomar (os.replace)" : "direkter R\u00fcckfall (r+b)";
    showModal(
      "Eintrag gel\u00f6scht",
      `Der Eintrag ${displayName} wurde aus der Datei gel\u00f6scht.\n\n` +
        "Der vorherige Stand wurde automatisch gesichert und kann bei Bedarf \u00fcber \u201eFr\u00fchere St\u00e4nde \u2026\u201c zur\u00fcckgeholt werden.",
      "ok"
    );
    appendTechDetails([
      `Sicherung: ${resp.backup_path}`,
      `Schreibmethode: ${methodText}`,
    ]);
  } catch (err) {
    handleApiError(err, "L\u00f6schen fehlgeschlagen");
  }
}

// Kurzbeschreibung (skos:note) ist einzeilig: Enter darf keinen Zeilenumbruch
// erzeugen, sondern wird wie eingefuegte Zeilenumbrueche zu einem Leerzeichen
// normalisiert (verhindert ungueltiges Turtle und bleibt fuer Mouseover sauber).
function setupNoteSingleLine() {
  const noteEl = document.getElementById("f-note");
  noteEl.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") return;
    ev.preventDefault();
    const start = noteEl.selectionStart ?? noteEl.value.length;
    const end = noteEl.selectionEnd ?? noteEl.value.length;
    const before = noteEl.value.slice(0, start);
    const after = noteEl.value.slice(end);
    const needsSpace = before.length > 0 && !/[ \t]$/.test(before) && !/^[ \t]/.test(after);
    const insert = needsSpace ? " " : "";
    noteEl.value = before + insert + after;
    const pos = start + insert.length;
    noteEl.setSelectionRange(pos, pos);
    if (insert || start !== end) markDirty();
  });
  noteEl.addEventListener("input", () => {
    if (!/[\r\n]/.test(noteEl.value)) return;
    const pos = noteEl.selectionStart ?? noteEl.value.length;
    const beforeNorm = normalizeSingleLine(noteEl.value.slice(0, pos));
    noteEl.value = normalizeSingleLine(noteEl.value);
    noteEl.setSelectionRange(beforeNorm.length, beforeNorm.length);
  });
}

// ---------------------------------------------------------------------
// Initialisierung
// ---------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("modal-close").addEventListener("click", hideModal);
  document.getElementById("toast-close").addEventListener("click", hideBanner);
  const toastBar = document.getElementById("toast-bar");
  toastBar.addEventListener("mouseenter", () => clearTimeout(toastTimer));
  toastBar.addEventListener("mouseleave", () => {
    if (!toastBar.hidden && toastAutoMs > 0) {
      toastTimer = setTimeout(hideBanner, 3000);
    }
  });

  document.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && ev.key.toLowerCase() === "s") {
      ev.preventDefault();
      if (App.state && App.state.path) saveAll();
      return;
    }
    if (ev.key === "Escape" && !document.getElementById("modal-overlay").classList.contains("hidden")) {
      if (typeof modalCancelHandler === "function") {
        modalCancelHandler();
      } else if (!document.getElementById("modal-box").classList.contains("no-close")) {
        hideModal();
      }
    }
  });

  document.getElementById("btn-validate-file").addEventListener("click", validateWholeFile);
  document.getElementById("btn-backup-menu").addEventListener("click", doOpenBackups);
  document.getElementById("btn-help").addEventListener("click", showHelp);
  document.getElementById("btn-rename").addEventListener("click", startRename);
  document.getElementById("btn-new-entry").addEventListener("click", startNewEntry);
  document.getElementById("btn-quit").addEventListener("click", doQuit);

  document.getElementById("btn-open").addEventListener("click", openFile);
  document.getElementById("btn-welcome-open").addEventListener("click", openFile);

  document.getElementById("tree-search").addEventListener("input", () => {
    clearTimeout(treeSearchTimer);
    treeSearchTimer = setTimeout(renderTree, 120);
  });
  document.getElementById("tree-type-filter").addEventListener("change", renderTree);

  document.querySelectorAll("#findings-filter .filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      App.findingFilter = btn.dataset.filter || "all";
      renderFindings();
    });
  });

  document.getElementById("btn-expand-all").addEventListener("click", () => {
    const term = document.getElementById("tree-search").value.trim().toLowerCase();
    const typeFilter = document.getElementById("tree-type-filter").value;
    const records = (App.state ? App.state.records : []).filter((r) => matchesFilter(r, term, typeFilter));
    for (const r of records) {
      const label = r.protected ? r.id : r.pref || r.id;
      App.expandedLetters.add(groupLetterFor(label));
    }
    renderTree();
  });
  document.getElementById("btn-collapse-all").addEventListener("click", () => {
    App.expandedLetters.clear();
    renderTree();
  });

  document.getElementById("btn-add-alt").addEventListener("click", () => {
    const r = addRow("alt-list", "", "z. B. Abk\u00fcrzung oder andere Schreibweise");
    const inp = r.querySelector("input.row-text");
    if (inp) inp.focus();
  });
  document.getElementById("btn-add-exact").addEventListener("click", () => {
    const r = addRow("exact-list", "", "z. B. https://d-nb.info/gnd/\u2026");
    const inp = r.querySelector("input.row-text");
    if (inp) inp.focus();
  });
  document.getElementById("btn-add-close").addEventListener("click", () => {
    const r = addRow("close-list", "", "z. B. https://de.wikipedia.org/wiki/\u2026");
    const inp = r.querySelector("input.row-text");
    if (inp) inp.focus();
  });
  setupRelatedPicker();
  setupNoteSingleLine();
  document.getElementById("f-id").addEventListener("input", () => {
    App.touchedFields.add("f-id");
    updateIdCheck();
  });
  document.getElementById("f-id").addEventListener("blur", () => {
    App.touchedFields.add("f-id");
    updateIdCheck();
  });
  for (const fieldId of ["f-pref", "f-note"]) {
    const el = document.getElementById(fieldId);
    el.addEventListener("input", () => {
      App.touchedFields.add(fieldId);
      updateFieldChecks(false);
    });
    el.addEventListener("blur", () => {
      App.touchedFields.add(fieldId);
      updateFieldChecks(false);
    });
  }
  document.getElementById("btn-close-file").addEventListener("click", doCloseFile);
  document.getElementById("btn-clear-search").addEventListener("click", () => {
    clearTimeout(treeSearchTimer);
    document.getElementById("tree-search").value = "";
    document.getElementById("tree-type-filter").value = "";
    renderTree();
    document.getElementById("tree-search").focus();
  });

  document.getElementById("concept-form").addEventListener("submit", onFormSubmit);
  document.getElementById("btn-save").addEventListener("click", saveAll);
  document.getElementById("btn-discard").addEventListener("click", discardCurrent);
  document.getElementById("concept-form").addEventListener("input", markDirty);
  document.getElementById("concept-form").addEventListener("change", markDirty);
  document.getElementById("btn-delete").addEventListener("click", onDeleteClick);

  window.addEventListener("beforeunload", (e) => {
    if (pendingCount()) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  try {
    App.state = await apiGet("/api/state");
  } catch {
    App.state = null;
  }
  renderTree();
  renderFindings();
  updatePathBar();
  updateFileControls();
  renderPending();
  refreshBackupStatus();
  await checkRecovery();
  setInterval(autosaveTick, 15000);
  setInterval(pingServer, PING_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkServerAlive();
  });
});
