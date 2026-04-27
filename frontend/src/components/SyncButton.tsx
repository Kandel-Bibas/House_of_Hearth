import { RefreshCw } from "lucide-react";
import clsx from "clsx";

import { useStartSync, useSyncStatus } from "../api/queries";
import { Button } from "./ui/button";

export function SyncButton() {
  const startSync = useStartSync();
  const status = useSyncStatus();
  const anyPending = status.data?.some((s) => s.last_sync_status === "pending");
  const busy = startSync.isPending || anyPending;

  return (
    <Button variant="outline" onClick={() => startSync.mutate()} disabled={busy}>
      <RefreshCw className={clsx("h-4 w-4", busy && "animate-spin")} />
      {busy ? "Syncing…" : "Sync now"}
    </Button>
  );
}
