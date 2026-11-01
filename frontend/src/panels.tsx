import { usePrefs, type PanelId } from "./state";
import type { ReactNode } from "react";

export function AnalyticalPanel({
  id,
  title,
  symbol,
  children,
}: {
  id: PanelId;
  title: string;
  symbol: string;
  children: ReactNode;
}) {
  const panel = usePrefs((state) => state.panels[id]);
  const expanded = usePrefs((state) => state.expandedPanel);
  const toggleCollapsed = usePrefs((state) => state.toggleCollapsed);
  const togglePinned = usePrefs((state) => state.togglePinned);
  const setExpandedPanel = usePrefs((state) => state.setExpandedPanel);
  const hidden = expanded !== null && expanded !== id;
  const open = !panel.collapsed && !hidden;
  return (
    <section
      className="pane analytic"
      data-testid={`panel-${id}`}
      data-collapsed={panel.collapsed || hidden}
      data-expanded={expanded === id}
      style={{ flexGrow: hidden ? 0 : panel.weight }}
    >
      <header className="pane-h">
        <h2>{title}{panel.pinnedSymbol ? ` · ${panel.pinnedSymbol}` : ""}</h2>
        <span className="pane-actions">
          <button aria-label={`Pin ${title}`} data-active={panel.pinnedSymbol === symbol} onClick={() => togglePinned(id, symbol)}>Pin</button>
          <button aria-label={expanded === id ? `Restore ${title}` : `Expand ${title}`} onClick={() => setExpandedPanel(expanded === id ? null : id)}>{expanded === id ? "Restore" : "Expand"}</button>
          <button aria-label={panel.collapsed ? `Open ${title}` : `Collapse ${title}`} onClick={() => toggleCollapsed(id)}>{panel.collapsed ? "Open" : "Collapse"}</button>
        </span>
      </header>
      {open && <div className="pane-b">{children}</div>}
    </section>
  );
}

export function PanelGrip({ left, right }: { left: PanelId; right: PanelId }) {
  const setPanelWeight = usePrefs((state) => state.setPanelWeight);
  return (
    <div
      className="grip"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${left} and ${right}`}
      onPointerDown={(event) => {
        event.preventDefault();
        const startX = event.clientX;
        const startLeft = usePrefs.getState().panels[left].weight;
        const startRight = usePrefs.getState().panels[right].weight;
        const move = (next: PointerEvent) => {
          const delta = (next.clientX - startX) / 220;
          setPanelWeight(left, Math.max(0.45, startLeft + delta));
          setPanelWeight(right, Math.max(0.45, startRight - delta));
        };
        const up = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
      }}
    />
  );
}
