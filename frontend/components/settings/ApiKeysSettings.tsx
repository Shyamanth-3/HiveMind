import { KeyRound, AlertTriangle } from "lucide-react";

// =============================================================================
// ApiKeysSettings — Centralized masked key display
// =============================================================================

const apiKeys = [
  { name: "GEMINI_API_KEY", set: true, service: "Google Gemini" },
  { name: "ANTHROPIC_API_KEY", set: false, service: "Anthropic Claude" },
  { name: "OPENAI_API_KEY", set: false, service: "OpenAI GPT" },
  { name: "SUPABASE_URL", set: true, service: "Supabase" },
  { name: "SUPABASE_SERVICE_KEY", set: true, service: "Supabase" },
  { name: "UPSTASH_REDIS_URL", set: true, service: "Upstash Redis" },
  { name: "UPSTASH_REDIS_TOKEN", set: true, service: "Upstash Redis" },
];

export function ApiKeysSettings() {
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-4">API Keys</h3>
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="space-y-3">
          {apiKeys.map((key) => (
            <div
              key={key.name}
              className="flex items-center justify-between rounded-lg bg-[var(--hm-surface-elevated)] px-4 py-3"
            >
              <div className="flex items-center gap-2.5">
                <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
                <div>
                  <p className="text-xs font-mono font-medium text-foreground">
                    {key.name}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {key.service}
                  </p>
                </div>
              </div>
              <span
                className={`text-[10px] font-medium ${
                  key.set ? "text-[var(--hm-success)]" : "text-muted-foreground"
                }`}
              >
                {key.set ? "✓ Configured" : "Not set"}
              </span>
            </div>
          ))}
        </div>

        {/* Security note */}
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-[var(--hm-warning)]/20 bg-[var(--hm-warning)]/5 px-3 py-2.5">
          <AlertTriangle className="h-3.5 w-3.5 text-[var(--hm-warning)] shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            Secrets are stored in environment variables and{" "}
            <span className="font-medium text-foreground">
              never committed to git
            </span>
            . API keys shown here are masked for display only.
          </p>
        </div>
      </div>
    </div>
  );
}
