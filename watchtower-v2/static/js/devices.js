/* =========================================================================
   Device Registry (Guardian redesign) — wired to /api/status, /api/ping-all,
   /api/command/<device>/<cmd>, /api/reset-brain. Reuses app.js helpers
   (onStatus, pingAll, openModal, closeAllModals, sendCommand, escapeHtml).

   Ported 2026-07-15 from the orphaned 7/9 redesign clone, with the alert
   banners (brain / M3 / pregame) grafted in from the old dashboard — the
   redesign predated them. The brain banner carries the Reset Brain button.
   ========================================================================= */
(function () {
  const root = document.getElementById("dr");
  if (!root) return;

  const el = (id) => document.getElementById(id);

  // ---- tiny svg glyphs -----------------------------------------------------
  const SVG = {
    alert: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    close: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  };

  // ---- lookups -------------------------------------------------------------
  function statusColor(s) {
    return { online: "#3DDC97", offline: "#F26D6D", testing: "#5AA2FF", unknown: "#6B6E8A" }[s] || "#6B6E8A";
  }
  function statusLabel(s) {
    return { online: "Online", offline: "Offline", testing: "Testing", unknown: "Untested" }[s] || s;
  }
  function badgeBg(s) {
    return { online: "rgba(61,220,151,.12)", offline: "rgba(242,109,109,.12)", testing: "rgba(90,162,255,.12)" }[s] || "#141726";
  }
  function roomColor(r) {
    return {
      "Systems": "#6C7AE0", "Zone Controller": "#7B68D9", "Zone Controllers": "#7B68D9",
      "Captain's Cabin": "#C4A265", "Ship Deck": "#4A90D9", "Jungle": "#45B7AA", "Cove": "#D97B9F",
    }[r] || "#6C7AE0";
  }
  const ROOM_ORDER = ["Zone Controller", "Zone Controllers", "Captain's Cabin", "Ship Deck", "Jungle", "Cove"];

  // ---- alert banners (brain / M3 / pregame) --------------------------------
  // Brain: driven by the "AI Character Brain" systems tile. The backend
  // escalates a silent brain to OFFLINE while a game is running (including
  // the "never came up" case that used to hide as a grey unknown tile);
  // "warn" (stale traffic, no game context) also alerts. Suppressed while a
  // reset is in flight so the button text doesn't flicker.
  let brainResetInFlight = false;
  function renderBrainAlert(systems) {
    const banner = el("brain-alert");
    if (!banner || brainResetInFlight) return;
    const brain = (systems || []).find(s => s.name === "AI Character Brain");
    const down = brain && (brain.status === "offline" || brain.status === "warn");
    banner.style.display = down ? "flex" : "none";
    if (down) {
      el("brain-alert-detail").textContent = brain.detail || "no RedBeard traffic";
      // If the launcher (the Reset receiver) is dead, the button can't work —
      // say so on the button itself rather than letting it fail silently.
      const btn = el("brain-reset-btn");
      if (btn) {
        if (brain.launcher_alive === false) {
          btn.disabled = true;
          btn.textContent = "⚠ Launcher down — use START bat";
        } else {
          btn.disabled = false;
          btn.textContent = "🔄 Reset Brain";
        }
      }
    }
  }

  function resetBrain() {
    const btn = el("brain-reset-btn");
    if (!btn || btn.disabled) return;
    brainResetInFlight = true;
    btn.disabled = true;
    btn.textContent = "⏳ Restarting…";
    fetch("/api/reset-brain", { method: "POST" })
      .then(r => r.json())
      .then(res => { btn.textContent = res.ok ? "✅ Restart sent" : "❌ Failed"; })
      .catch(() => { btn.textContent = "❌ Failed"; })
      .finally(() => {
        // Give the brain time to relaunch + publish its heartbeat before the
        // banner re-evaluates (heartbeat interval is 30s).
        setTimeout(() => {
          brainResetInFlight = false;
          btn.disabled = false;
          btn.textContent = "🔄 Reset Brain";
        }, 15000);
      });
  }
  const brainBtn = el("brain-reset-btn");
  if (brainBtn) brainBtn.onclick = resetBrain;

  function renderM3Alert(m3) {
    const banner = el("m3-alert");
    if (!banner) return;
    const show = !!(m3 && m3.needed);
    banner.style.display = show ? "flex" : "none";
    if (show) {
      el("m3-alert-headline").textContent = m3.headline || "M3 needs a restart";
      el("m3-alert-detail").textContent = m3.detail || "";
      banner.classList.toggle("offline", m3.level === "offline");
    }
  }

  function renderPregameAlert(pre) {
    const banner = el("pregame-alert");
    if (!banner) return;
    const issues = (pre && pre.issues) || [];
    banner.style.display = issues.length ? "flex" : "none";
    if (issues.length) {
      const list = el("pregame-alert-list");
      list.innerHTML = "";
      issues.forEach(it => {
        const row = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = `${it.icon || "⚠️"} ${it.name}`;
        const detail = document.createElement("span");
        detail.textContent = it.detail ? ` — ${it.detail}` : "";
        detail.style.opacity = "0.8";
        row.appendChild(name);
        row.appendChild(detail);
        list.appendChild(row);
      });
    }
  }

  // 24/7 health sentinel: findings raised WITHOUT any scan (dead sensors,
  // silent boards, WiFi flapping, dead AI launcher…). Red if any finding is
  // an error, amber if only warnings. Rows are built with createElement so
  // detail text can never inject HTML.
  function renderHealthAlert(health) {
    const banner = el("health-alert");
    if (!banner) return;
    const finds = (health && health.findings) || [];
    banner.style.display = finds.length ? "flex" : "none";
    if (!finds.length) return;
    const hasError = finds.some(f => f.severity === "error");
    banner.classList.toggle("dr-banner-red", hasError);
    banner.classList.toggle("dr-banner-amber", !hasError);
    el("health-alert-title").textContent =
      `WatchTower spotted ${finds.length} problem${finds.length > 1 ? "s" : ""} — no scan needed`;
    const list = el("health-alert-list");
    list.innerHTML = "";
    finds.forEach(f => {
      const row = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = `${f.severity === "error" ? "🔴" : "🟡"} ${f.title}`;
      const detail = document.createElement("span");
      detail.textContent = ` — ${f.detail}`;
      detail.style.opacity = "0.8";
      row.appendChild(name);
      row.appendChild(detail);
      list.appendChild(row);
    });
  }

  // ---- status strip --------------------------------------------------------
  function renderStrip(counts) {
    counts = counts || {};
    const set = (id, v) => { const e = el(id); if (e) e.textContent = v; };
    set("dr-c-online", counts.online || 0);
    set("dr-c-offline", counts.offline || 0);
    set("dr-c-unknown", counts.unknown || 0);
    set("dr-c-testing", counts.testing || 0);
  }

  // ---- attention band (real offline devices) -------------------------------
  function renderAttention(devices) {
    const box = el("dr-attention");
    if (!box) return;
    const offline = Object.entries(devices).filter(([, d]) => d.status === "offline");
    if (!offline.length) { box.style.display = "none"; box.innerHTML = ""; return; }
    box.style.display = "flex";
    box.innerHTML = offline.map(([name, d]) => `
      <div class="dr-alert">
        <span class="dr-alert-ic">${SVG.alert}</span>
        <div class="dr-alert-body">
          <div class="dr-alert-title">${escapeHtml(name)} is offline</div>
          <div class="dr-alert-sub">${escapeHtml(d.error || "No ping response — its puzzle is dead until it answers.")}</div>
        </div>
        <button class="dr-alert-btn" data-name="${escapeHtml(name)}">Inspect</button>
      </div>`).join("");
    box.querySelectorAll(".dr-alert-btn").forEach(btn => {
      btn.onclick = () => openDeviceModal(btn.dataset.name, devices[btn.dataset.name]);
    });
  }

  // ---- section shell -------------------------------------------------------
  function sectionEl(roomName, countLabel, cardEls) {
    const rc = roomColor(roomName);
    const sec = document.createElement("section");
    sec.className = "dr-section";
    const head = document.createElement("div");
    head.className = "dr-room-head";
    head.innerHTML = `
      <span class="dr-room-square" style="background:${rc};box-shadow:0 0 12px ${rc};"></span>
      <h2 class="dr-room-title">${escapeHtml(roomName)}</h2>
      <span class="dr-room-count">${escapeHtml(countLabel)}</span>
      <div class="dr-room-rule"></div>`;
    const grid = document.createElement("div");
    grid.className = "dr-grid";
    cardEls.forEach(c => grid.appendChild(c));
    sec.appendChild(head);
    sec.appendChild(grid);
    return sec;
  }

  // ---- device card ---------------------------------------------------------
  function deviceCard(name, dev) {
    const s = dev.status;
    const sc = statusColor(s);
    const rc = roomColor(dev.room);
    const ms = dev.response_ms;

    let msLabel = "", msColor = "#6f7392";
    if (s === "offline") { msLabel = "—"; msColor = "#F26D6D"; }
    else if (dev.type === "bac") { msLabel = ms != null ? ms + "s" : "—"; }
    else { msLabel = ms != null ? ms + "ms" : "—"; }

    let barPct = 40, barColor = rc;
    if (s === "online") { barColor = dev.type === "bac" ? rc : "#3DDC97"; barPct = Math.max(28, Math.min(100, 100 - (ms || 40) / 12)); }
    else if (s === "testing") { barColor = "#5AA2FF"; barPct = 52; }
    else if (s === "offline") { barColor = "#F26D6D"; barPct = 8; }
    else { barColor = "#3a3e58"; barPct = 26; }  // unknown / untested

    const accent = s === "online" ? rc : sc;
    const border = s === "offline" ? "rgba(242,109,109,.35)" : "var(--border)";

    const btn = document.createElement("button");
    btn.className = "dr-card";
    btn.style.borderColor = border;
    btn.innerHTML = `
      <span class="dr-card-accent" style="background:${accent};"></span>
      <div class="dr-card-top">
        <span class="dot${s === "online" ? " pulse" : ""}" style="background:${sc};"></span>
        <span class="dr-card-name">${escapeHtml(name)}</span>
        <span class="dr-card-ms" style="color:${msColor};">${escapeHtml(msLabel)}</span>
      </div>
      <div class="dr-card-status-row">
        <span class="dr-card-status" style="color:${sc};">${escapeHtml(statusLabel(s))}</span>
      </div>
      <div class="dr-bar"><span class="dr-bar-fill" style="width:${barPct}%;background:${barColor};"></span></div>`;
    btn.onclick = () => openDeviceModal(name, dev);
    return btn;
  }

  // ---- systems tile --------------------------------------------------------
  function systemCard(sys) {
    // system statuses: online / offline / warn / unknown
    const map = { online: "#3DDC97", offline: "#F26D6D", warn: "#F6B24A", unknown: "#6B6E8A" };
    const lbl = { online: "Online", offline: "Offline", warn: "Check", unknown: "Idle" };
    const sc = map[sys.status] || "#6B6E8A";
    const accent = sys.status === "online" ? "#6C7AE0" : sc;
    const card = document.createElement("div");
    card.className = "dr-card dr-static";
    card.innerHTML = `
      <span class="dr-card-accent" style="background:${accent};"></span>
      <div class="dr-card-top">
        <span class="dot${sys.status === "online" ? " pulse" : ""}" style="background:${sc};"></span>
        <span class="dr-card-name">${escapeHtml(sys.name)}</span>
      </div>
      <div class="dr-card-status-row">
        <span class="dr-card-status" style="color:${sc};">${escapeHtml(lbl[sys.status] || sys.status)}</span>
      </div>
      ${sys.detail ? `<div class="dr-card-detail" title="${escapeHtml(sys.detail)}">${escapeHtml(sys.detail)}</div>` : ""}`;
    return card;
  }

  // ---- character mic tiles: ship + jungle (live input level) -----------------------------
  function micPct(mic) {
    const level = mic.level || 0;
    const fullScale = (mic.speak_ok || 600) * 1.5;
    return Math.max(0, Math.min(100, (level / fullScale) * 100));
  }
  function micCard(mic) {
    const s = mic.status === "offline" ? "offline" : mic.status === "unknown" ? "unknown" : "online";
    const sc = statusColor(s);
    const label = { online: "Hearing", idle: "Live (quiet)", offline: "No signal", unknown: "Starting…" }[mic.status] || "Live";
    const pct = micPct(mic);
    const card = document.createElement("button");
    card.className = "dr-card";
    card.innerHTML = `
      <span class="dr-card-accent" style="background:${sc};"></span>
      <div class="dr-card-top">
        <span class="dot${s !== "offline" ? " pulse" : ""}" style="background:${sc};"></span>
        <span class="dr-card-name">${escapeHtml(mic.name || "Pirate Ship Mic")}</span>
      </div>
      <div class="dr-card-status-row">
        <span class="dr-card-status" style="color:${sc};">${escapeHtml(label)}</span>
      </div>
      <div class="dr-bar dr-bar-mic"><span class="dr-bar-fill" style="width:${pct}%;"></span></div>`;
    // A synthetic device object so the detail modal works for the mic too.
    const dev = {
      type: "mic", status: mic.status === "offline" ? "offline" : "online", room: mic.room || "Ship Deck",
      topic: mic.topic && mic.topic !== "—" ? mic.topic : null, commands: [],
      error: mic.error, _micLevel: mic.level,
    };
    card.onclick = () => openDeviceModal(mic.name || "Pirate Ship Mic", dev);
    return card;
  }

  // ---- rooms ---------------------------------------------------------------
  function renderRooms(data) {
    const container = el("dr-rooms");
    if (!container) return;
    container.innerHTML = "";

    // 1) Systems infrastructure tiles
    const systems = data.systems || [];
    if (systems.length) {
      const online = systems.filter(s => s.status === "online").length;
      container.appendChild(sectionEl("Systems", `${online}/${systems.length} online`, systems.map(systemCard)));
    }

    // 2) Group real devices by room
    const devices = data.devices || {};
    const groups = {}, seen = [];
    for (const [name, dev] of Object.entries(devices)) {
      if (dev.room === "Systems") continue;  // Systems owns its own section
      const room = dev.room || "Other";
      if (!groups[room]) { groups[room] = []; seen.push(room); }
      groups[room].push([name, dev]);
    }

    // Character mics (Pirate Ship -> Ship Deck, Jungle -> Jungle): each tile
    // lands in its own room; make sure that room section exists.
    const mics = (data.mics && data.mics.length ? data.mics : (data.mic ? [data.mic] : []))
      .filter(m => m && m.status);
    const micsByRoom = {};
    mics.forEach(m => {
      const room = m.room || "Ship Deck";
      (micsByRoom[room] = micsByRoom[room] || []).push(m);
      if (!groups[room]) { groups[room] = []; seen.push(room); }
    });

    // Ordered: preferred rooms first, then any extras alphabetically
    const ordered = seen.slice().sort((a, b) => {
      const ia = ROOM_ORDER.indexOf(a), ib = ROOM_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });

    ordered.forEach(room => {
      const list = groups[room];
      const cards = list.map(([name, dev]) => deviceCard(name, dev));
      let total = list.length;
      let online = list.filter(([, d]) => d.status === "online").length;
      (micsByRoom[room] || []).forEach(m => {
        cards.push(micCard(m)); total += 1;
        if (m.status === "online" || m.status === "idle") online += 1;
      });
      container.appendChild(sectionEl(room, `${online}/${total} online`, cards));
    });
  }

  // ---- device detail modal -------------------------------------------------
  function openDeviceModal(name, dev) {
    if (!dev) return;
    const s = dev.status;
    const sc = statusColor(s);
    const rc = roomColor(dev.room);
    const typeU = (dev.type || "").toUpperCase();
    const roomLine = (dev.room ? dev.room + " · " : "") + typeU;

    let resp;
    if (dev.type === "mic") resp = dev._micLevel != null ? "live · level " + Math.round(dev._micLevel) : "live";
    else if (s === "offline") resp = "no response";
    else if (dev.response_ms != null) resp = dev.type === "bac" ? dev.response_ms + "s ago" : dev.response_ms + "ms";
    else resp = "—";

    const topic = dev.topic ? "MermaidsTale/" + dev.topic : "—";
    const cmds = dev.commands || [];
    const cmdBlock = cmds.length ? `
      <div class="dr-modal-label">Commands</div>
      <div class="dr-cmds">${cmds.map(c => `<button class="dr-cmd" data-cmd="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join("")}</div>` : "";

    const issues = dev.error
      ? `<div class="dr-issue"><span class="dot offline"></span><span class="dr-issue-title">${escapeHtml(dev.error)}</span></div>`
      : `<div class="dr-noissue">No issues logged</div>`;

    const html = `
      <div class="gd-modal show dr-modal">
        <div class="dr-modal-head">
          <span class="dr-modal-chip" style="background:${rc}22;border:1px solid ${rc}55;">
            <span class="dr-modal-chip-dot" style="background:${rc};"></span>
          </span>
          <div class="dr-modal-titles">
            <div class="dr-modal-name">${escapeHtml(name)}</div>
            <div class="dr-modal-room">${escapeHtml(roomLine)}</div>
          </div>
          <span class="dr-modal-badge" style="color:${sc};background:${badgeBg(s)};">${escapeHtml(statusLabel(s))}</span>
          <button class="dr-modal-close" onclick="closeAllModals()">${SVG.close}</button>
        </div>
        <div class="dr-modal-body">
          <div class="dr-modal-grid">
            <div class="dr-stat"><div class="dr-stat-label">Type</div><div class="dr-stat-val">${escapeHtml(typeU || "—")}</div></div>
            <div class="dr-stat"><div class="dr-stat-label">Response</div><div class="dr-stat-val">${escapeHtml(resp)}</div></div>
            <div class="dr-stat full"><div class="dr-stat-label">MQTT topic</div><div class="dr-stat-val topic">${escapeHtml(topic)}</div></div>
          </div>
          ${cmdBlock}
          <div class="dr-manifest-block" style="display:none;">
            <div class="dr-modal-label">Manifest</div>
            <div class="dr-modal-grid dr-manifest-grid"></div>
          </div>
          <div class="dr-modal-label">Recent issues</div>
          <div class="dr-issues">${issues}</div>
        </div>
      </div>`;

    openModal(html);

    document.querySelectorAll("#modal-container .dr-cmd").forEach(btn => {
      btn.onclick = () => {
        const cmd = btn.dataset.cmd;
        sendCommand(name, cmd);
        btn.textContent = cmd + " ✓";
        btn.classList.add("sent");
        setTimeout(() => { btn.textContent = cmd; btn.classList.remove("sent"); }, 2000);
      };
    });

    // Manifest data (firmware/board/commands) — same source as the old modal.
    fetch(`/api/manifests/${name}`)
      .then(r => r.ok ? r.json() : null)
      .then(manifest => {
        if (!manifest || manifest.error) return;
        const block = document.querySelector("#modal-container .dr-manifest-block");
        const grid = document.querySelector("#modal-container .dr-manifest-grid");
        if (!block || !grid) return;
        const rows = [
          ["Firmware", manifest.firmware_version],
          ["Board", manifest.board_type],
          ["Build", manifest.build_status],
          ["Commands", manifest.supported_commands],
          ["Listens on", manifest.subscribe_topics],
          ["Publishes", manifest.publish_topics],
        ].filter(([, v]) => v);
        if (!rows.length) return;
        grid.innerHTML = rows.map(([k, v]) =>
          `<div class="dr-stat full"><div class="dr-stat-label">${escapeHtml(k)}</div><div class="dr-stat-val">${escapeHtml(v)}</div></div>`).join("");
        block.style.display = "block";
      })
      .catch(() => {});

    // Recent debug-log entries for this device — same source as the old modal.
    fetch(`/api/debug-log?device=${encodeURIComponent(name)}`)
      .then(r => r.json())
      .then(data => {
        const div = document.querySelector("#modal-container .dr-issues");
        if (!div || !data.entries || !data.entries.length) return;
        div.innerHTML = data.entries.slice(0, 5).map(e => `
          <div class="dr-issue">
            <span class="dot ${e.resolved ? "idle" : "offline"}"></span>
            <span class="dr-issue-title">${escapeHtml(e.title)}</span>
          </div>`).join("");
      })
      .catch(() => {});
  }

  // ---- ping all boards -----------------------------------------------------
  const pingBtn = el("dr-ping");
  if (pingBtn) {
    pingBtn.onclick = () => {
      pingAll();
      pingBtn.disabled = true;
      const swept = el("dr-swept");
      if (swept) swept.textContent = "Sweeping boards…";
      setTimeout(() => {
        pingBtn.disabled = false;
        if (swept) {
          const t = new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
          swept.textContent = "Swept " + t;
        }
      }, 1600);
    };
  }

  // ---- wiring --------------------------------------------------------------
  function apply(data) {
    if (!data) return;
    renderStrip(data.counts);
    renderBrainAlert(data.systems);
    renderM3Alert(data.m3_restart);
    renderPregameAlert(data.pregame);
    renderHealthAlert(data.health);
    renderAttention(data.devices || {});
    renderRooms(data);
  }

  onStatus(apply);
  // Paint immediately, before the first shared poll tick.
  fetch("/api/status").then(r => r.json()).then(apply).catch(() => {});
})();
