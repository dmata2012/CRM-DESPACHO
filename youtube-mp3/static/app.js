const $ = (id) => document.getElementById(id);
let currentUrl = "";

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

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Error inesperado");
  return data;
}

$("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage("");
  $("result").hidden = true;
  $("search-btn").disabled = true;
  $("search-btn").textContent = "Buscando...";
  currentUrl = $("url").value.trim();

  try {
    const info = await postJSON("/api/info", { url: currentUrl });
    $("thumb").src = info.thumbnail || "";
    $("title").textContent = info.title;
    $("meta").textContent = `${info.channel || ""} · ${formatDuration(info.duration)}`;
    $("bitrate").innerHTML = info.bitrates
      .map((b) => `<option value="${b}" ${b === "192" ? "selected" : ""}>MP3 ${b} kbps</option>`)
      .join("");
    $("convert-btn").disabled = info.too_long;
    $("progress-box").hidden = true;
    $("download-btn").hidden = true;
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

$("convert-btn").addEventListener("click", async () => {
  showMessage("");
  $("convert-btn").disabled = true;
  $("download-btn").hidden = true;
  $("progress-box").hidden = false;
  setProgress(0, "En cola...");

  try {
    const { job_id } = await postJSON("/api/convert", {
      url: currentUrl,
      bitrate: $("bitrate").value,
    });
    pollStatus(job_id);
  } catch (err) {
    showMessage(err.message);
    $("convert-btn").disabled = false;
  }
});

function setProgress(pct, text) {
  $("bar").style.width = `${pct}%`;
  $("progress-text").textContent = text;
}

const STATUS_TEXT = {
  queued: "En cola...",
  downloading: "Descargando audio...",
  converting: "Convirtiendo a MP3...",
};

async function pollStatus(jobId) {
  try {
    const res = await fetch(`/api/status/${jobId}`);
    const job = await res.json();
    if (!res.ok || job.status === "error") throw new Error(job.error || "La conversión falló");

    if (job.status === "done") {
      const mb = (job.size / 1048576).toFixed(1);
      setProgress(100, `Listo · ${mb} MB`);
      $("download-btn").href = `/api/download/${jobId}`;
      $("download-btn").textContent = `Descargar ${job.filename}`;
      $("download-btn").hidden = false;
      $("convert-btn").disabled = false;
      return;
    }
    setProgress(job.progress, `${STATUS_TEXT[job.status] || ""} ${Math.round(job.progress)}%`);
    setTimeout(() => pollStatus(jobId), 1000);
  } catch (err) {
    showMessage(err.message);
    $("progress-box").hidden = true;
    $("convert-btn").disabled = false;
  }
}
