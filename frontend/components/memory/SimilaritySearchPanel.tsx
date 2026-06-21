"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Search, Sparkles } from "lucide-react";

// =============================================================================
// SimilaritySearchPanel — Semantic search demo with mocked top-k results
// =============================================================================

interface SimilarityResult {
  content: string;
  source: string;
  similarity: number;
}

const mockSimilarityResults: Record<string, SimilarityResult[]> = {
  bakery: [
    { content: "Local bakery websites typically feature high-quality food photography, warm color palettes...", source: "web_search:bakery_website_best_practices", similarity: 0.94 },
    { content: "Menu page layout: categorize items (Breads, Pastries, Cakes, Beverages)...", source: "web_search:bakery_menu_design", similarity: 0.87 },
    { content: "E-commerce ordering patterns for small bakeries: simple cart sidebar...", source: "web_search:bakery_ordering_patterns", similarity: 0.82 },
  ],
  dental: [
    { content: "Dental clinic websites prioritize trust signals: professional certifications...", source: "web_search:dental_clinic_web_design", similarity: 0.96 },
    { content: "Common dental services to feature: General Dentistry, Cosmetic Dentistry...", source: "web_search:dental_services_list", similarity: 0.89 },
    { content: "Healthcare testimonials pattern: use patient first name + last initial...", source: "web_search:healthcare_testimonials", similarity: 0.83 },
  ],
  default: [
    { content: "Contact form best practices: include name, email, phone (optional)...", source: "web_search:contact_form_patterns", similarity: 0.78 },
    { content: "Form validation for ordering: validate quantity > 0, validate cart not empty...", source: "memory_recall:run_001", similarity: 0.72 },
  ],
};

function getSimilarityColor(score: number): string {
  if (score >= 0.9) return "text-[var(--hm-success)]";
  if (score >= 0.8) return "text-[var(--hm-primary)]";
  return "text-[var(--hm-warning)]";
}

export function SimilaritySearchPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SimilarityResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = () => {
    if (!query.trim()) return;
    setHasSearched(true);

    const lowerQuery = query.toLowerCase();
    if (lowerQuery.includes("bakery") || lowerQuery.includes("menu")) {
      setResults(mockSimilarityResults.bakery);
    } else if (lowerQuery.includes("dental") || lowerQuery.includes("clinic")) {
      setResults(mockSimilarityResults.dental);
    } else {
      setResults(mockSimilarityResults.default);
    }
  };

  return (
    <div className="hm-glass rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="h-4 w-4 text-[var(--hm-primary)]" />
        <h3 className="text-sm font-semibold text-foreground">
          Similarity Search
        </h3>
      </div>

      {/* Search Input */}
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder='Try "bakery website design" or "dental clinic"...'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className={cn(
              "h-9 w-full rounded-lg border border-border bg-background pl-9 pr-3",
              "text-sm text-foreground placeholder:text-muted-foreground",
              "focus:border-[var(--hm-primary)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--hm-primary)]/30"
            )}
          />
        </div>
        <button
          onClick={handleSearch}
          className="rounded-lg bg-[var(--hm-primary)] px-4 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90"
        >
          Search
        </button>
      </div>

      {/* Results */}
      <div className="space-y-2">
        {!hasSearched && (
          <p className="text-xs text-muted-foreground text-center py-4">
            Enter a query to find semantically similar memory chunks
          </p>
        )}
        {hasSearched && results.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">
            No similar chunks found
          </p>
        )}
        {results.map((result, i) => (
          <div
            key={i}
            className="rounded-lg border border-border bg-background/50 px-4 py-3 transition-colors hover:bg-[var(--hm-surface-elevated)]"
          >
            <div className="flex items-start justify-between gap-3 mb-1.5">
              <p className="text-xs text-foreground leading-relaxed flex-1">
                {result.content}
              </p>
              <span
                className={cn(
                  "text-sm font-bold tabular-nums shrink-0",
                  getSimilarityColor(result.similarity)
                )}
              >
                {result.similarity.toFixed(2)}
              </span>
            </div>
            <span className="text-[10px] font-mono text-muted-foreground">
              {result.source}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
