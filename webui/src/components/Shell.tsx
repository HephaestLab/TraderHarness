import {
  Activity,
  Bot,
  ChartNoAxesCombined,
  GitCompareArrows,
  LayoutDashboard,
  Radio,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { to: "/", label: "工作台", icon: LayoutDashboard },
  { to: "/agents", label: "智能体", icon: Bot },
  { to: "/live", label: "实时运行", icon: Radio },
  { to: "/results", label: "回测结果", icon: ChartNoAxesCombined },
  { to: "/compare", label: "智能体对比", icon: GitCompareArrows },
];

export function Shell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            TH
          </span>
          <span>
            <strong>TraderHarness</strong>
            <small>交易智能体研究台</small>
          </span>
        </div>
        <nav className="nav" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="system-state">
            <i />
            本地运行环境
            <Activity size={14} />
          </div>
          <p>历史数据与访问凭据始终保留在本机。</p>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <span className="breadcrumb">智能体研究 / A 股市场</span>
          <div className="topbar-meta">
            <span>● 系统就绪</span>
            <span>严格时序遮罩</span>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
