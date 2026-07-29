(function () {
  const format = (value, digits = 3) =>
    typeof value === "number" ? value.toFixed(digits) : "—";

  const metric = (label, value) => `
    <div class="ab-metric"><small>${label}</small><strong>${value}</strong></div>`;

  function conditionMarkup(condition) {
    const metrics = condition.metrics || {};
    const passed = condition.audit.status === "pass";
    const pending = condition.audit.status === "pending";
    const auditText = pending
      ? "Leakage audit pending"
      : passed
      ? `PASS · ${condition.audit.finding_count} findings`
      : `${condition.audit.finding_count} expected findings retained`;
    const rows = (condition.runs || []).map((run) => `
      <tr>
        <td>${run.id}</td>
        <td>${format(run.metrics.total_return_pct, 4)}%</td>
        <td>${format(run.metrics.alpha_pct, 4)}%</td>
        <td>${format(run.metrics.total_trades, 0)}</td>
        <td>${Number(run.llm_total_tokens || 0).toLocaleString()}</td>
      </tr>`).join("");
    return `
      <div class="ab-config">
        <span>Date masking <b>${condition.mask_dates ? "ON" : "OFF"}</b></span>
        <span>Entity masking <b>${condition.mask_entities ? "ON" : "OFF"}</b></span>
        <span class="${passed ? "pass" : pending ? "" : "control"}">${auditText}</span>
      </div>
      <div class="ab-metrics">
        ${metric("Mean return", `${format(metrics.total_return_pct, 4)}%`)}
        ${metric("Alpha vs CSI 300", `${format(metrics.alpha_pct, 4)}%`)}
        ${metric("Sharpe", format(metrics.sharpe_ratio))}
        ${metric("Max drawdown", `${format(metrics.max_drawdown_pct, 4)}%`)}
      </div>
      <div class="ab-table-wrap">
        <table><thead><tr><th>Run</th><th>Return</th><th>Alpha</th><th>Trades</th><th>Tokens</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5">Pilot execution is pending.</td></tr>'}</tbody></table>
      </div>`;
  }

  async function mount(root) {
    if (root.dataset.ready === "true") return;
    root.dataset.ready = "true";
    try {
      const response = await fetch(root.dataset.artifact, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      root.innerHTML = `
        <div class="ab-meta">
          <span><small>Model</small>${data.model}</span>
          <span><small>Window</small>${data.window.start} → ${data.window.end}</span>
          <span><small>Paired repetitions</small>${data.repetitions}</span>
          <span><small>Status</small>${data.status}</span>
        </div>
        <div class="ab-tabs" role="tablist" aria-label="Experiment condition">
          <button type="button" role="tab" aria-selected="true" data-condition="masked">Masked</button>
          <button type="button" role="tab" aria-selected="false" data-condition="unmasked">Unmasked control</button>
        </div>
        <div class="ab-condition" role="tabpanel"></div>
        <div class="ab-boundary"><strong>Interpretation boundary</strong><ul>${data.limitations.map((item) => `<li>${item}</li>`).join("")}</ul></div>`;
      const panel = root.querySelector(".ab-condition");
      const activate = (name) => {
        root.querySelectorAll("[data-condition]").forEach((button) => {
          button.setAttribute("aria-selected", String(button.dataset.condition === name));
        });
        panel.innerHTML = conditionMarkup(data.conditions[name]);
      };
      root.querySelectorAll("[data-condition]").forEach((button) =>
        button.addEventListener("click", () => activate(button.dataset.condition)));
      activate("masked");
    } catch (error) {
      root.innerHTML = `<div class="ab-error" role="alert">Could not load the experiment artifact: ${error.message}</div>`;
    }
  }

  function boot() {
    document.querySelectorAll("[data-masking-showcase]").forEach(mount);
  }
  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(boot);
  } else {
    document.addEventListener("DOMContentLoaded", boot);
  }
})();
