(function () {
  if (!window.CHANNEL_CONNECTED) return;

  let chart = null;

  function fmt(n) {
    if (n == null) return "—";
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toLocaleString("es");
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function showReconnectBanner(message) {
    const main = document.querySelector(".dash-layout");
    if (!main) return;
    const existing = document.getElementById("reconnect-banner");
    if (existing) existing.remove();

    const banner = document.createElement("div");
    banner.id = "reconnect-banner";
    banner.className = "panel dash-full";
    banner.innerHTML = `
      <div class="panel-head"><span>conexión_perdida</span></div>
      <div class="panel-body" style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;">
        <p style="color:var(--text-dim);max-width:48ch;">${esc(message || "Tu conexión con YouTube expiró o fue revocada.")}</p>
        <a href="/youtube/connect" class="btn btn-primary">Reconectar canal con Google →</a>
      </div>
    `;
    main.prepend(banner);

    const videosEl = document.getElementById("videos-list");
    if (videosEl) videosEl.innerHTML = '<p style="color:var(--text-dim);font-size:0.875rem;">Reconectá tu canal para ver los videos.</p>';
  }

  async function loadData() {
    try {
      const res = await fetch("/api/overview");
      const data = await res.json();
      if (!res.ok) {
        if (data.reconnect) {
          showReconnectBanner(data.error);
        } else {
          console.error(data.error);
        }
        return;
      }
      renderMetrics(data.analytics.totals, data.analytics.days);
      renderChart(data.analytics.daily, data.analytics.days);
      renderVideos(data.videos);
      const subEl = document.getElementById("sub-count");
      if (subEl && data.channel) {
        subEl.textContent = fmt(data.channel.subscriber_count) + " suscriptores";
      }
    } catch (e) {
      console.error(e);
    }
  }

  function renderMetrics(t, days) {
    document.getElementById("m-views").textContent = fmt(t.views);
    document.getElementById("m-minutes").textContent = fmt(t.minutes_watched);
    document.getElementById("m-gained").textContent = "+" + fmt(t.subs_gained);
    const net = (t.subs_gained || 0) - (t.subs_lost || 0);
    const netEl = document.getElementById("m-net");
    netEl.textContent = (net >= 0 ? "+" : "") + fmt(net);
    netEl.className = "metric-value " + (net >= 0 ? "positive" : "negative");
    const lbl = document.getElementById("chart-label");
    if (lbl) lbl.textContent = `últimos ${days} días`;
  }

  function renderChart(daily, days) {
    const labels = daily.map(d => {
      const dt = new Date(d.date);
      return dt.toLocaleDateString("es", { month: "short", day: "numeric" });
    });
    const views = daily.map(d => d.views);
    const ctx = document.getElementById("chart");
    if (!ctx) return;
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Vistas",
          data: views,
          borderColor: "#4F8EF7",
          backgroundColor: "rgba(79,142,247,0.08)",
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#111827",
            borderColor: "#1F2D45",
            borderWidth: 1,
            titleColor: "#6B7FA3",
            bodyColor: "#E2E8F4",
          },
        },
        scales: {
          x: { grid: { color: "#1F2D45" }, ticks: { color: "#6B7FA3", font: { family: "JetBrains Mono", size: 11 } } },
          y: { grid: { color: "#1F2D45" }, ticks: { color: "#6B7FA3", font: { family: "JetBrains Mono", size: 11 } } },
        },
      },
    });
  }

  function renderVideos(videos) {
    const el = document.getElementById("videos-list");
    if (!el) return;
    if (!videos || videos.length === 0) {
      el.innerHTML = '<p style="color:var(--text-dim);font-size:0.875rem;">No se encontraron videos.</p>';
      return;
    }
    el.innerHTML = videos.map(v => `
      <div class="video-row">
        <img class="video-thumb" src="${esc(v.thumbnail)}" alt="" loading="lazy">
        <div class="video-title" title="${esc(v.title)}">${esc(v.title)}</div>
        <div class="video-stat"><strong>${fmt(v.views)}</strong>vistas</div>
        <div class="video-stat"><strong>${fmt(v.likes)}</strong>likes</div>
        <div class="video-stat"><strong>${fmt(v.comments)}</strong>comentarios</div>
      </div>
    `).join("");
  }

  // Refresh
  const refreshBtn = document.getElementById("refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", loadData);

  // Exportar Excel
  const exportBtn = document.getElementById("export-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      exportBtn.disabled = true;
      exportBtn.textContent = "Generando…";
      window.location.href = "/api/export/excel";
      setTimeout(() => {
        exportBtn.disabled = false;
        exportBtn.textContent = "↓ Exportar Excel";
      }, 4000);
    });
  }

  // Upgrade a Pro
  async function startUpgrade() {
    try {
      const res = await fetch("/payments/checkout-pro", { method: "POST", headers: { "Content-Type": "application/json" } });
      const data = await res.json();
      if (data.checkout_url) {
        // Redirigir a MercadoPago Checkout
        window.location.href = data.checkout_url;
      } else {
        alert(data.error || "Error iniciando pago.");
      }
    } catch (e) { alert("Error de red."); }
  }

  ["upgrade-btn", "upgrade-btn-2"].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", startUpgrade);
  });

  // Init
  loadData();
})();
