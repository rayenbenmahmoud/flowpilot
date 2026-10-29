import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./components/Auth";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { Dashboard } from "./pages/Dashboard";
import { Executions, ExecutionView } from "./pages/Executions";
import { GuidedDemo } from "./pages/GuidedDemo";
import { Integrations } from "./pages/Integrations";
import { Login } from "./pages/Login";
import { Outputs } from "./pages/Outputs";
import { WorkflowEditor } from "./pages/WorkflowEditor";
import { Workflows } from "./pages/Workflows";

export function App() {
  const { ready, username, config } = useAuth();
  if (!ready) return <Spinner label="Starting FlowPilot" />;
  if (!username) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="workflows" element={<Workflows />} />
        <Route path="workflows/new" element={<WorkflowEditor />} />
        <Route path="workflows/:id" element={<WorkflowEditor />} />
        <Route path="executions" element={<Executions />} />
        <Route path="executions/:id" element={<ExecutionView />} />
        <Route path="outputs" element={<Outputs />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="demo" element={config?.demo_mode ? <GuidedDemo /> : <Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
