import { useEffect, useState } from "react";
import { usePlaidLink, PlaidLinkOnSuccessMetadata } from "react-plaid-link";
import { Plus } from "lucide-react";

import { useExchangePublicToken, useLinkToken } from "../api/queries";

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
    <button
      onClick={handleClick}
      disabled={busy}
      className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
    >
      <Plus className="h-4 w-4" />
      {busy ? "Connecting…" : "Add Account"}
    </button>
  );
}
