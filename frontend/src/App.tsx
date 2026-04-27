import { Outlet } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
