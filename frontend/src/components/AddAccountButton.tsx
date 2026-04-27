import { useEffect, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import type { PlaidLinkOnSuccessMetadata } from "react-plaid-link";
import { Plus } from "lucide-react";

import { useExchangePublicToken, useLinkToken } from "../api/queries";
import { Button } from "./ui/button";

export function AddAccountButton() {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const linkTokenMutation = useLinkToken();
  const exchangeMutation = useExchangePublicToken();

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess: (publicToken: string, _metadata: PlaidLinkOnSuccessMetadata) => {
      exchangeMutation.mutate(publicToken);
      setLinkToken(null);
    },
    onExit: () => {
      setLinkToken(null);
    },
  });

  useEffect(() => {
    if (linkToken && ready) {
      open();
    }
  }, [linkToken, ready, open]);

  const handleClick = async () => {
    const result = await linkTokenMutation.mutateAsync();
    setLinkToken(result.link_token);
  };

  const busy = linkTokenMutation.isPending || exchangeMutation.isPending || (!!linkToken && !ready);

  return (
    <Button onClick={handleClick} disabled={busy}>
      <Plus className="h-4 w-4" />
      {busy ? "Connecting…" : "Add Account"}
    </Button>
  );
}
