import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type ToastKind = "success" | "error" | "info";

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<((kind: ToastKind, message: string) => void) | null>(null);

const ICONS: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const LABELS: Record<ToastKind, string> = {
  success: "成功",
  error: "错误",
  info: "提示",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++;
      setItems((current) => [...current.slice(-4), { id, kind, message }]);
      window.setTimeout(() => dismiss(id), 4000);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-stack" role="region" aria-label="通知">
        {items.map((item) => {
          const Icon = ICONS[item.kind];
          return (
            <div key={item.id} className={`toast ${item.kind}`} role="status">
              <Icon size={16} aria-label={LABELS[item.kind]} />
              <span>{item.message}</span>
              <button
                className="toast-close"
                aria-label="关闭通知"
                onClick={() => dismiss(item.id)}
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Toast access hook. Outside a ToastProvider it degrades to a no-op so that
 * components remain testable in isolation.
 */
export function useToast(): ToastApi {
  const push = useContext(ToastContext);
  return useMemo(() => {
    const emit = push ?? (() => undefined);
    return {
      success: (message: string) => emit("success", message),
      error: (message: string) => emit("error", message),
      info: (message: string) => emit("info", message),
    };
  }, [push]);
}
