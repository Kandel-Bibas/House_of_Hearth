import { RefreshCw } from "lucide-react";
import clsx from "clsx";

import { useStartSync, useSyncStatus } from "../api/queries";

export function SyncButton() {
  const startSync = useStartSync();
  const status = useSyncStatus();
  const anyPending = status.data?.some((s) => s.last_sync_status === "pending");

  return (
    <button
      onClick={() => startSync.mutate()}
      disabled={startSync.isPending || anyPending}
      className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
    >
      <RefreshCw className={clsx("h-4 w-4", (startSync.isPending || anyPending) && "animate-spin")} />
      {startSync.isPending || anyPending ? "Syncing…" : "Sync now"}
    </button>
  );
}
