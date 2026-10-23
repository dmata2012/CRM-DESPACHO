const $ = (id) => document.getElementById(id);
let current = null; // video buscado: { url, info }
let pollTimer = null;
const downloaded = new Set(); // trabajos ya descargados automáticamente

function showMessage(text) {
  $("message").textContent = text;
  $("message").hidden = !text;
}

function formatDuration(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = String(sec % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

async function request(url, options = {}) {
  const res = await fetch(url, options);
  const data = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Error inesperado");
  return data;
}

const postJSON = (url, body) =>
  request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// --- Búsqueda --------------------------------------------------------------

$("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage("");
  $("result").hidden = true;
  $("search-btn").disabled = true;
  $("search-btn").textContent = "Buscando...";
  const url = $("url").value.trim();

  try {
    const info = await postJSON("/api/info", { url });
    current = { url, info };
    $("thumb").src = info.thumbnail || "";
    $("title").textContent = info.title;
    $("meta").textContent = `${info.channel || ""} · ${formatDuration(info.duration)}`;

    const lastFormat = localGet("format") || "mp3";
    $("format").innerHTML = info.formats
      .map((f) => `<option value="${f.id}" ${f.id === lastFormat ? "selected" : ""}>${f.label}</option>`)
      .join("");
    const lastBitrate = localGet("bitrate") || "192";
    $("bitrate").innerHTML = info.bitrates
      .map((b) => `<option value="${b}" ${b === lastBitrate ? "selected" : ""}>${b} kbps</option>`)
      .join("");
    updateBitrateVisibility();

    $("add-btn").disabled = info.too_long;
    $("result").hidden = false;
    if (info.too_long) {
      showMessage(`El video supera el máximo de ${formatDuration(info.max_duration)}.`);
    }
  } catch (err) {
    showMessage(err.message);
  } finally {
    $("search-btn").disabled = false;
    $("search-btn").textContent = "Buscar";
  }
});

function updateBitrateVisibility() {
  const fmt = current?.info.formats.find((f) => f.id === $("format").value);
  $("bitrate-label").hidden = !fmt?.uses_bitrate;
}
$("format").addEventListener("change", updateBitrateVisibility);

// --- Agregar a la cola -----------------------------------------------------

$("add-btn").addEventListener("click", async () => {
  if (!current) return;
  showMessage("");
  $("add-btn").disabled = true;
  $("add-btn").textContent = "Agregando...";
  const format = $("format").value;
  const bitrate = $("bitrate").value;
  localSet("format", format);
  localSet("bitrate", bitrate);

  try {
    await postJSON("/api/convert", { url: current.url, format, bitrate });
    // Listo para el siguiente enlace
    $("result").hidden = true;
    $("url").value = "";
    $("url").focus();
    current = null;
    refreshQueue();
  } catch (err) {
    showMessage(err.message);
  } finally {
    $("add-btn").disabled = false;
    $("add-btn").textContent = "Agregar a la cola";
  }
});

// --- Cola ------------------------------------------------------------------

const STATUS_TEXT = {
  queued: (j) => `En espera · posición ${j.position}`,
  downloading: (j) => `Descargando audio... ${Math.round(j.progress)}%`,
  converting: () => "Convirtiendo...",
  done: (j) => `Listo · ${(j.size / 1048576).toFixed(1)} MB`,
  error: (j) => j.error || "La conversión falló",
};

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function renderJob(j) {
  const quality = j.bitrate ? ` · ${j.bitrate} kbps` : "";
  let action = "";
  if (j.status === "done") {
    action = `<a class="download" href="/api/download/${j.id}">Descargar</a>
              <button class="remove secondary" data-id="${j.id}" title="Quitar">✕</button>`;
  } else if (j.status === "queued") {
    action = `<button class="remove secondary" data-id="${j.id}">Cancelar</button>`;
  } else if (j.status === "error") {
    action = `<button class="remove secondary" data-id="${j.id}" title="Quitar">✕</button>`;
  }
  return `
    <li class="job ${j.status}">
      <img src="${escapeHtml(j.thumbnail)}" alt="">
      <div class="job-info">
        <p class="job-title">${escapeHtml(j.title)}</p>
        <p class="meta">${escapeHtml(j.format_label)}${quality} · ${formatDuration(j.duration)}</p>
        <div class="progress"><div style="width:${j.progress}%"></div></div>
        <p class="job-status">${escapeHtml(STATUS_TEXT[j.status](j))}</p>
      </div>
      <div class="job-actions">${action}</div>
    </li>`;
}

async function refreshQueue() {
  clearTimeout(pollTimer);
  try {
    const { jobs } = await request("/api/jobs");
    $("queue-section").hidden = jobs.length === 0;
    $("queue").innerHTML = jobs.map(renderJob).join("");
    const pending = jobs.filter((j) => !["done", "error"].includes(j.status)).length;
    $("queue-count").textContent = pending ? `(${pending} pendiente${pending > 1 ? "s" : ""})` : "";

    // Descarga automática al terminar cada conversión
    for (const j of jobs) {
      if (j.status === "done" && !downloaded.has(j.id)) {
        downloaded.add(j.id);
        if ($("auto-download").checked) triggerDownload(j.id);
      }
    }
    if (pending) pollTimer = setTimeout(refreshQueue, 1000);
  } catch (err) {
    showMessage(err.message);
    pollTimer = setTimeout(refreshQueue, 3000);
  }
}

function triggerDownload(jobId) {
  const a = document.createElement("a");
  a.href = `/api/download/${jobId}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

$("queue").addEventListener("click", async (e) => {
  const btn = e.target.closest(".remove");
  if (!btn) return;
  try {
    await request(`/api/jobs/${btn.dataset.id}`, { method: "DELETE" });
  } catch (err) {
    showMessage(err.message);
  }
  refreshQueue();
});

$("clear-btn").addEventListener("click", async () => {
  const done = [...document.querySelectorAll(".job.done .remove, .job.error .remove")];
  await Promise.all(
    done.map((b) => request(`/api/jobs/${b.dataset.id}`, { method: "DELETE" }).catch(() => {}))
  );
  refreshQueue();
});

// --- Preferencias (formato y calidad recordados) ---------------------------

function localGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function localSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* sin almacenamiento */ }
}

$("auto-download").checked = localGet("autoDownload") !== "0";
$("auto-download").addEventListener("change", (e) =>
  localSet("autoDownload", e.target.checked ? "1" : "0")
);

// Al abrir la página no se re-descargan los trabajos ya terminados
request("/api/jobs")
  .then(({ jobs }) => jobs.filter((j) => j.status === "done").forEach((j) => downloaded.add(j.id)))
  .finally(refreshQueue);
