import { KeyRound, PlugZap, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNotice, PageHeader } from "../components/Metric";
import { useToast } from "../components/Toast";
import { llmSourceLabel } from "../locale";
import type { LLMConfig, LLMTestResult } from "../types";

interface TestOutcome extends LLMTestResult {
  elapsed: number;
}

export function Settings() {
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [error, setError] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("deepseek-chat");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [outcome, setOutcome] = useState<TestOutcome | null>(null);
  const toast = useToast();

  const refresh = () =>
    api
      .getLLMConfig()
      .then(setConfig)
      .catch((reason: Error) => setError(reason.message));

  useEffect(() => {
    void refresh();
  }, []);

  const credentialPayload = () => {
    const payload: { api_key?: string; base_url?: string } = {};
    if (apiKey.trim()) payload.api_key = apiKey.trim();
    if (baseUrl.trim()) payload.base_url = baseUrl.trim();
    return payload;
  };

  const save = async () => {
    setSaving(true);
    try {
      const next = await api.saveLLMConfig(credentialPayload());
      setConfig(next);
      setApiKey("");
      toast.success("LLM 设置已保存");
    } catch (reason) {
      toast.error((reason as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!window.confirm("确定清空页面保存的 LLM 设置？环境变量中的凭据不受影响。")) return;
    try {
      const next = await api.saveLLMConfig({ clear: true });
      setConfig(next);
      setApiKey("");
      setBaseUrl("");
      toast.success("已清空页面保存的 LLM 设置");
    } catch (reason) {
      toast.error((reason as Error).message);
    }
  };

  const test = async () => {
    setTesting(true);
    setOutcome(null);
    const started = performance.now();
    try {
      const result = await api.testLLMConfig({
        ...credentialPayload(),
        model: model.trim() || undefined,
      });
      const elapsed = (performance.now() - started) / 1000;
      setOutcome({ ...result, elapsed });
      if (result.ok) toast.success(`连接成功（${elapsed.toFixed(1)} 秒）`);
      else toast.error(`连接失败：${result.detail}`);
    } catch (reason) {
      toast.error((reason as Error).message);
    } finally {
      setTesting(false);
    }
  };

  return (
    <section>
      <PageHeader
        eyebrow="系统设置"
        title="LLM API 配置"
        description="配置大模型 API Key 与请求地址，保存后回测与实时运行立即生效。"
      />
      {error ? <ErrorNotice message={error} /> : null}
      <div className="section-grid settings-grid">
        <div className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">当前状态</span>
              <h2>生效凭据</h2>
            </div>
            <KeyRound size={20} aria-hidden="true" />
          </div>
          {config ? (
            <dl className="settings-status">
              <div>
                <dt>配置状态</dt>
                <dd>
                  <span className={`status-dot ${config.configured ? "ok" : "err"}`} />
                  {config.configured ? "已配置" : "未配置"}
                </dd>
              </div>
              <div>
                <dt>凭据来源</dt>
                <dd>{llmSourceLabel(config.source)}</dd>
              </div>
              <div>
                <dt>API Key</dt>
                <dd className="mono">{config.api_key_masked || "—"}</dd>
              </div>
              <div>
                <dt>请求地址</dt>
                <dd className="mono">{config.base_url || "—"}</dd>
              </div>
              <div>
                <dt>地址来源</dt>
                <dd>{llmSourceLabel(config.base_url_source)}</dd>
              </div>
            </dl>
          ) : (
            <p className="empty-state">正在读取配置…</p>
          )}
          <ul className="settings-notes">
            <li>环境变量（DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL）优先级高于页面设置。</li>
            <li>API Key 仅保存在本机 ~/.traderharness/settings.json，不会进入任何回测结果或日志。</li>
            <li>本服务仅监听本机回环地址，请勿暴露到公网。</li>
          </ul>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">凭据管理</span>
              <h2>更新凭据</h2>
            </div>
          </div>
          <form
            className="run-form"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <label>
              <span>API Key</span>
              <input
                type="password"
                autoComplete="off"
                placeholder={
                  config?.api_key_masked
                    ? `当前：${config.api_key_masked}（留空表示不修改）`
                    : "sk-..."
                }
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
            </label>
            <label>
              <span>请求地址 Base URL</span>
              <input
                type="text"
                placeholder="https://api.deepseek.com"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
              />
            </label>
            <label>
              <span>测试模型</span>
              <input
                type="text"
                placeholder="deepseek-chat"
                value={model}
                onChange={(event) => setModel(event.target.value)}
              />
            </label>
            <div className="form-submit">
              <span>留空的字段保持当前值不变；「清空设置」会删除页面保存的全部凭据。</span>
              <div className="settings-actions">
                <button
                  type="button"
                  className="button secondary"
                  disabled={testing}
                  onClick={() => void test()}
                >
                  <PlugZap size={16} />
                  {testing ? "测试中…" : "测试连接"}
                </button>
                <button type="button" className="button danger" onClick={() => void clear()}>
                  <Trash2 size={16} />
                  清空设置
                </button>
                <button
                  className="button primary"
                  disabled={saving || (!apiKey.trim() && !baseUrl.trim())}
                >
                  <Save size={16} />
                  保存设置
                </button>
              </div>
            </div>
          </form>
          {outcome ? (
            <div
              className={outcome.ok ? "notice-ok settings-test-result" : "notice-error settings-test-result"}
              role="status"
            >
              {outcome.ok
                ? `连接成功 · 模型 ${outcome.model} · 耗时 ${outcome.elapsed.toFixed(1)} 秒`
                : `连接失败 · 模型 ${outcome.model} · ${outcome.detail}`}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
