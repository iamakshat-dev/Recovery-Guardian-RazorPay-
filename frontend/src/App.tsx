import { useState } from "react";
import { AppShell } from "./components/shell/AppShell";
import { NAV_ITEMS } from "./components/shell/navigation";
import { ComingSoon } from "./pages/ComingSoon";
import { DecisionPipeline } from "./pages/DecisionPipeline";
import { Explainability } from "./pages/Explainability";
import { IncidentReplay } from "./pages/IncidentReplay";
import { Overview } from "./pages/Overview";
import { SafetyHero } from "./pages/SafetyHero";

function App() {
  const [activeSection, setActiveSection] = useState("overview");

  const activeItem = NAV_ITEMS.find((item) => item.id === activeSection);

  let content;
  if (activeSection === "overview") {
    content = <Overview />;
  } else if (activeSection === "safety") {
    content = <SafetyHero />;
  } else if (activeSection === "decision-pipeline") {
    content = <DecisionPipeline />;
  } else if (activeSection === "explainability") {
    content = <Explainability />;
  } else if (activeSection === "incident-replay") {
    content = <IncidentReplay />;
  } else {
    content = <ComingSoon label={activeItem?.label ?? "Section"} />;
  }

  return (
    <AppShell activeSection={activeSection} onNavigate={setActiveSection}>
      {content}
    </AppShell>
  );
}

export default App;
