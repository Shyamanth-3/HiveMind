"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/PageHeader";
import { MemorySearchBar } from "@/components/memory/MemorySearchBar";
import { KnowledgeStats } from "@/components/memory/KnowledgeStats";
import { MemoryChunkTable } from "@/components/memory/MemoryChunkTable";
import { SimilaritySearchPanel } from "@/components/memory/SimilaritySearchPanel";
import { MemoryPipelineDiagram } from "@/components/memory/MemoryPipelineDiagram";

// =============================================================================
// Memory Page — Knowledge Base (RAG)
// =============================================================================

export default function MemoryPage() {
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Knowledge Base"
        subtitle="RAG-powered memory system — search by meaning, not just keywords."
      />

      <MemorySearchBar value={searchQuery} onChange={setSearchQuery} />

      <KnowledgeStats />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <MemoryChunkTable />
        </div>
        <div className="lg:col-span-2">
          <SimilaritySearchPanel />
        </div>
      </div>

      <MemoryPipelineDiagram />
    </div>
  );
}