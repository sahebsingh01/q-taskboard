import { Link, useNavigate } from "react-router-dom";
import { clearSession, getStoredUser } from "@/lib/api-client";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function Header() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState<string>("");

  useEffect(() => {
    const u = getStoredUser();
    if (u) setName(u.name);
  }, []);

  function onLogout() {
    clearSession();
    // Drop cached data (incl. permissions) so the next user never sees ours.
    queryClient.clear();
    navigate("/login");
  }

  return (
    <header className="border-b border-border bg-surface">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/dashboard" className="text-lg font-semibold">
          TaskBoard
        </Link>
        <div className="flex items-center gap-4">
          {name && <span className="text-sm text-muted">{name}</span>}
          <button
            onClick={onLogout}
            className="text-sm text-muted hover:text-white"
          >
            sign out
          </button>
        </div>
      </div>
    </header>
  );
}
