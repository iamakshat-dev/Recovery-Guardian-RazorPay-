import { useState } from "react";
import { AppShell } from "./components/shell/AppShell";
import { NAV_ITEMS } from "./components/shell/navigation";
import { ComingSoon } from "./pages/ComingSoon";
import { Overview } from "./pages/Overview";

function App() {
  const [activeSection, setActiveSection] = useState("overview");

  const activeItem = NAV_ITEMS.find((item) => item.id === activeSection);
  const content = activeSection === "overview" ? <Overview /> : <ComingSoon label={activeItem?.label ?? "Section"} />;

  return (
    <AppShell activeSection={activeSection} onNavigate={setActiveSection}>
      {content}
    </AppShell>
  );
}

export default App;
