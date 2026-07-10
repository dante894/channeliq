(function () {
  let retentionChart = null;
  let retentionData = [];

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

  async function loadData() {
    try {
      const res = await fetch("/api/pro-stats");
      const data = await res.json();
      if (!res.ok) {
        if (data.upgrade) {
          document.querySelector(".pro-layout").innerHTML =
            '<div class="panel"><div class="panel-body locked-panel"><h2>Esta sección es exclusiva de Pro</h2></div></div>';
          return;
        }
        console.error(data.error);
        return;
      }
      renderComparison(data.comparison);
      renderTraffic(data.traffic);
      renderRanking(data.top_videos);
      renderRetention(data.retention);
    } catch (e) {
      console.error(e);
    }
  }

  function renderComparison(cmp) {
    if (!cmp) return;
    const label = document.getElementById("compare-label");
    if (label) label.textContent = `últimos ${cmp.days} días vs ${cmp.days} días anteriores`;

    const fields = [
      { key: "views", label: "Vistas" },
      { key: "minutes_watched", label: "Minutos vistos" },
      { key: "subs_gained", label: "Subs ganados" },
      { key: "likes", label: "Likes" },
    ];
    const row = document.getElementById("compare-row");
    row.innerHTML = fields.map(f => {
      const val = cmp.current[f.key];
      const change = cmp.changes[f.key];
      const up = change >= 0;
      return `
        <div class="compare-card">
          <div class="compare-label">${f.label}</div>
          <div class="compare-value">${fmt(val)}</div>
          <span class="compare-delta ${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${Math.abs(change)}%</span>
        </div>
      `;
    }).join("");
  }

  function renderTraffic(sources) {
    const el = document.getElementById("traffic-list");
    if (!el) return;
    if (!sources || sources.length === 0) {
      el.innerHTML = '<p style="color:var(--text-dim);font-size:0.875rem;">Sin datos de tráfico todavía.</p>';
      return;
    }
    el.innerHTML = sources.map(s => `
      <div class="traffic-row">
        <div class="traffic-name">${esc(s.source)}</div>
        <div class="traffic-bar-bg"><div class="traffic-bar-fill" style="width:${s.pct}%"></div></div>
        <div class="traffic-pct">${fmt(s.views)} · ${s.pct}%</div>
      </div>
    `).join("");
  }

  function renderRanking(videos) {
    const el = document.getElementById("rank-list");
    if (!el) return;
    if (!videos || videos.length === 0) {
      el.innerHTML = '<p style="color:var(--text-dim);font-size:0.875rem;">No se encontraron videos en este período.</p>';
      return;
    }
    el.innerHTML = videos.map((v, i) => `
      <div class="rank-row">
        <div class="rank-num">#${i + 1}</div>
        <img class="rank-thumb" src="${esc(v.thumbnail)}" alt="" loading="lazy">
        <div class="rank-title" title="${esc(v.title)}">${esc(v.title)}</div>
        <div class="rank-stat"><strong>${fmt(v.views)}</strong>vistas</div>
        <div class="rank-stat"><strong>${fmt(v.likes)}</strong>likes</div>
        <div class="rank-stat"><strong>${fmt(v.comments)}</strong>coment.</div>
        <div class="rank-stat"><strong>${v.avg_view_pct}%</strong>retención</div>
      </div>
    `).join("");
  }

  function renderRetention(videos) {
    retentionData = videos || [];
    const tabsEl = document.getElementById("retention-tabs");
    if (!tabsEl) return;
    if (retentionData.length === 0) {
      tabsEl.innerHTML = "";
      document.querySelector(".retention-chart-wrap").innerHTML =
        '<p style="color:var(--text-dim);font-size:0.875rem;">No hay datos de retención disponibles.</p>';
      return;
    }
    tabsEl.innerHTML = retentionData.map((v, i) => `
      <button class="retention-tab ${i === 0 ? 'active' : ''}" data-idx="${i}" title="${esc(v.title)}">${esc(v.title)}</button>
    `).join("");
    tabsEl.querySelectorAll(".retention-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        tabsEl.querySelectorAll(".retention-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        drawRetentionChart(parseInt(btn.dataset.idx, 10));
      });
    });
    drawRetentionChart(0);
  }

  function drawRetentionChart(idx) {
    const v = retentionData[idx];
    const ctx = document.getElementById("retention-chart");
    if (!ctx || !v) return;
    if (retentionChart) retentionChart.destroy();

    if (!v.curve || v.curve.length === 0) {
      ctx.getContext("2d").clearRect(0, 0, ctx.width, ctx.height);
      return;
    }

    retentionChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: v.curve.map(p => p.t + "%"),
        datasets: [{
          label: "Retención",
          data: v.curve.map(p => p.retention),
          borderColor: "#4F8EF7",
          backgroundColor: "rgba(79,142,247,0.08)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25,
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
            callbacks: {
              title: (items) => `Video visto en ${items[0].label}`,
              label: (item) => `Retención: ${item.formattedValue}%`,
            },
          },
        },
        scales: {
          x: { grid: { color: "#1F2D45" }, ticks: { color: "#6B7FA3", font: { family: "JetBrains Mono", size: 10 }, maxTicksLimit: 10 } },
          y: { min: 0, max: 100, grid: { color: "#1F2D45" }, ticks: { color: "#6B7FA3", font: { family: "JetBrains Mono", size: 11 } } },
        },
      },
    });
  }

  const refreshBtn = document.getElementById("refresh-pro-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", loadData);

  loadData();
})();
