(function () {
  const format = (value, digits = 3) =>
    typeof value === "number" ? value.toFixed(digits) : "—";

  const metric = (label, value) => `
    <div class="ab-metric"><small>${label}</small><strong>${value}</strong></div>`;

  const messages = {
    en: {
      auditPending: "Leakage audit pending",
      auditPassed: (count) => `PASS · ${count} findings`,
      auditRetained: (count) => `${count} expected findings retained`,
      dateMasking: "Date masking",
      entityMasking: "Entity masking",
      enabled: "ON",
      disabled: "OFF",
      meanReturn: "Mean return",
      alpha: "Alpha vs CSI 300",
      sharpe: "Sharpe",
      maxDrawdown: "Max drawdown",
      run: "Run",
      return: "Return",
      tableAlpha: "Alpha",
      trades: "Trades",
      tokens: "Tokens",
      pending: "Pilot execution is pending.",
      model: "Model",
      window: "Window",
      repetitions: "Paired repetitions",
      status: "Status",
      statusValues: {},
      experimentCondition: "Experiment condition",
      masked: "Masked",
      unmasked: "Unmasked control",
      boundary: "Interpretation boundary",
      limitations: (items) => items,
      loadError: "Could not load the experiment artifact",
    },
    zh: {
      auditPending: "泄漏审计待执行",
      auditPassed: (count) => `通过 · ${count} 项发现`,
      auditRetained: (count) => `保留 ${count} 项预期发现`,
      dateMasking: "日期掩码",
      entityMasking: "实体掩码",
      enabled: "开启",
      disabled: "关闭",
      meanReturn: "平均收益率",
      alpha: "相对沪深 300 超额收益",
      sharpe: "夏普比率",
      maxDrawdown: "最大回撤",
      run: "运行",
      return: "收益率",
      tableAlpha: "超额收益",
      trades: "交易次数",
      tokens: "Token 数",
      pending: "试运行尚未执行。",
      model: "模型",
      window: "时间窗口",
      repetitions: "配对重复次数",
      status: "状态",
      statusValues: { recorded: "已录制", complete: "已完成", pending: "待执行" },
      experimentCondition: "实验条件",
      masked: "已掩码",
      unmasked: "未掩码对照组",
      boundary: "解读边界",
      limitations: () => [
        "这是已录制的研究实验，不是实时回测或投资建议。",
        "结果仅作描述性试验。表现差异本身不能证明模型存在记忆、数据污染或因果行为。",
      ],
      loadError: "无法加载实验工件",
    },
  };

  function conditionMarkup(condition, copy) {
    const metrics = condition.metrics || {};
    const passed = condition.audit.status === "pass";
    const pending = condition.audit.status === "pending";
    const auditText = pending
      ? copy.auditPending
      : passed
      ? copy.auditPassed(condition.audit.finding_count)
      : copy.auditRetained(condition.audit.finding_count);
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
        <span>${copy.dateMasking} <b>${condition.mask_dates ? copy.enabled : copy.disabled}</b></span>
        <span>${copy.entityMasking} <b>${condition.mask_entities ? copy.enabled : copy.disabled}</b></span>
        <span class="${passed ? "pass" : pending ? "" : "control"}">${auditText}</span>
      </div>
      <div class="ab-metrics">
        ${metric(copy.meanReturn, `${format(metrics.total_return_pct, 4)}%`)}
        ${metric(copy.alpha, `${format(metrics.alpha_pct, 4)}%`)}
        ${metric(copy.sharpe, format(metrics.sharpe_ratio))}
        ${metric(copy.maxDrawdown, `${format(metrics.max_drawdown_pct, 4)}%`)}
      </div>
      <div class="ab-table-wrap">
        <table><thead><tr><th>${copy.run}</th><th>${copy.return}</th><th>${copy.tableAlpha}</th><th>${copy.trades}</th><th>${copy.tokens}</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="5">${copy.pending}</td></tr>`}</tbody></table>
      </div>`;
  }

  async function mount(root) {
    if (root.dataset.ready === "true") return;
    root.dataset.ready = "true";
    const copy = document.documentElement.lang.toLowerCase().startsWith("zh")
      ? messages.zh
      : messages.en;
    try {
      const response = await fetch(root.dataset.artifact, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      root.innerHTML = `
        <div class="ab-meta">
          <span><small>${copy.model}</small>${data.model}</span>
          <span><small>${copy.window}</small>${data.window.start} → ${data.window.end}</span>
          <span><small>${copy.repetitions}</small>${data.repetitions}</span>
          <span><small>${copy.status}</small>${copy.statusValues[data.status] || data.status}</span>
        </div>
        <div class="ab-tabs" role="tablist" aria-label="${copy.experimentCondition}">
          <button type="button" role="tab" aria-selected="true" data-condition="masked">${copy.masked}</button>
          <button type="button" role="tab" aria-selected="false" data-condition="unmasked">${copy.unmasked}</button>
        </div>
        <div class="ab-condition" role="tabpanel"></div>
        <div class="ab-boundary"><strong>${copy.boundary}</strong><ul>${copy.limitations(data.limitations).map((item) => `<li>${item}</li>`).join("")}</ul></div>`;
      const panel = root.querySelector(".ab-condition");
      const activate = (name) => {
        root.querySelectorAll("[data-condition]").forEach((button) => {
          button.setAttribute("aria-selected", String(button.dataset.condition === name));
        });
        panel.innerHTML = conditionMarkup(data.conditions[name], copy);
      };
      root.querySelectorAll("[data-condition]").forEach((button) =>
        button.addEventListener("click", () => activate(button.dataset.condition)));
      activate("masked");
    } catch (error) {
      root.innerHTML = `<div class="ab-error" role="alert">${copy.loadError}: ${error.message}</div>`;
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
