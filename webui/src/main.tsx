import { Component, StrictMode, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

class ErrorBoundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("TraderHarness UI error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="fatal-error">
          <span>界面运行错误</span>
          <h1>研究工作台无法正常渲染。</h1>
          <pre>{this.state.error.message}</pre>
          <button className="button primary" onClick={() => window.location.reload()}>
            重新加载工作台
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
