import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Dock, Palette, Ribbon, Stage } from "./shell";
import { useSession } from "./feed";
import { usePrefs } from "./state";
import { Depth, Execution, PortfolioView, Pulse, QueryLab, ReplayStudio, RiskView, Systems, TapeWorkspace } from "./views";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Workstation />
    </QueryClientProvider>
  );
}

function Workstation() {
  useSession();
  const workspace = usePrefs((state) => state.workspace);
  const density = usePrefs((state) => state.density);
  const reduced = usePrefs((state) => state.reducedMotion);
  const setWorkspace = usePrefs((state) => state.setWorkspace);
  const setPalette = usePrefs((state) => state.setPalette);
  const palette = usePrefs((state) => state.palette);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette(!palette);
        return;
      }
      if (typing) return;
      if (event.key === "Escape") setPalette(false);
      const index = "123456789".indexOf(event.key);
      if (index >= 0) {
        const ids = ["pulse", "depth", "tape", "execution", "portfolio", "risk", "replay", "query", "systems"] as const;
        setWorkspace(ids[index]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [palette, setPalette, setWorkspace]);
  const view = {
    pulse: <Pulse />,
    depth: <Depth />,
    tape: <TapeWorkspace />,
    execution: <Execution />,
    portfolio: <PortfolioView />,
    risk: <RiskView />,
    replay: <ReplayStudio />,
    query: <QueryLab />,
    systems: <Systems />,
  }[workspace];
  return (
    <div className="shell" data-density={density} data-motion={reduced ? "reduce" : "full"}>
      <Ribbon />
      <Stage>{view}</Stage>
      <Dock />
      <Palette />
    </div>
  );
}
