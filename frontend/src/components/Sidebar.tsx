import { NavLink } from "react-router-dom";
import { LayoutDashboard, ListChecks, Wallet, TrendingUp } from "lucide-react";
import clsx from "clsx";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/transactions", label: "Transactions", icon: ListChecks },
  { to: "/accounts", label: "Accounts", icon: Wallet },
  { to: "/holdings", label: "Holdings", icon: TrendingUp },
];

export function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r border-border bg-card p-4">
      <h1 className="text-xl font-semibold mb-6">Finance Tracker</h1>
      <ul className="flex flex-col gap-1">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                  isActive ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-100"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
