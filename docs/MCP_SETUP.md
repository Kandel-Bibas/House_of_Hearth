# Wiring the Finance Tracker MCP server into Claude Desktop

The MCP server is a local stdio process. Claude Desktop launches it on demand via a config entry.

## One-time setup

1. Open `~/Library/Application Support/Claude/claude_desktop_config.json` in your editor.
   If it doesn't exist, create it with `{"mcpServers": {}}`.

2. Add this entry under `mcpServers` (merge with any existing entries):

   ```json
   {
     "mcpServers": {
       "finance-tracker": {
         "command": "/Users/bibas/personal/finance-tracker/.venv/bin/python",
         "args": ["-m", "mcp_server"],
         "cwd": "/Users/bibas/personal/finance-tracker",
         "env": {
           "DATABASE_URL": "sqlite:///finance.db"
         }
       }
     }
   }
   ```

3. Restart Claude Desktop. Open a new chat and ask "what MCP tools do you have?"
   Claude should list the 5 finance-tracker tools.

## Verifying it works

In Claude Desktop, after restart, ask: "What's my net worth?" — Claude will call the
`net_worth` tool and report the values from your local DB.

## Common issues

- **"Schema out of date" errors from every tool** — open `~/Desktop/Finance Tracker.command`
  once. The startup hook runs Alembic, then MCP queries work.
- **Tool errors mentioning Keychain** — none should occur. The MCP server never imports
  `core.crypto`. If you see one, something is wrong; please re-run the test suite
  (`make test`) before reporting.
- **Claude Desktop says "MCP server failed to start"** — open the Claude Desktop logs
  (Help → Open Logs Folder) and look for the `finance-tracker` server's stderr. Common
  causes: wrong path to `.venv/bin/python`, project moved, venv deleted.

## Tools exposed

- `search_transactions(start_date?, end_date?, account_id?, category_primary?, category_detailed?, merchant_name?, min_amount?, max_amount?, include_removed?, limit?)` — filtered transaction list.
- `net_worth()` — total + per-account-type breakdown.
- `category_spend(start_date, end_date)` — outflow by primary category.
- `list_holdings()` — current investment positions.
- `list_accounts()` — linked accounts with sync status.

## Security posture

- The MCP process opens SQLite in read-only mode (`?mode=ro`) — even a bug cannot write to your DB.
- It does not import `core.crypto` and has no path to Plaid. The worst case is "an agent reads your spending data," never "an agent fetches your bank statements live."
- Plaid access tokens (which DO grant bank-read access) live encrypted in the same SQLite file under the `items.access_token_ciphertext` column, and the MCP server cannot decrypt them.
