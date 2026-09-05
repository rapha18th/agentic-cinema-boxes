export type DepthName = "scout" | "production" | "kubrick";

export interface ProjectRecord {
  id: string;
  premise: string;
  depth: DepthName;
  status: string;
  confidence?: number;
  coverage?: number;
  source_diversity?: number;
  provenance_quality?: number;
  unresolved_contradictions?: number;
  progress?: Record<string, unknown>;
  error?: string;
  stop_reason?: string;
  overview?: string;
  title?: string;
  created_at?: number;
  updated_at?: number;
}

export interface ResearchBox {
  id: string;
  name: string;
  description?: string;
  rationale?: string;
  score?: number;
  evidence_count?: number;
  distinct_domains?: number;
  emergent?: boolean;
  departments?: string[];
  summary?: string;
}

export interface Evidence {
  id: string;
  text?: string;
  url?: string;
  title?: string;
  source_domain?: string;
  publish_date?: string;
  modality?: string;
  objective_id?: string;
  query?: string;
  relevance_reason?: string;
  license_note?: string;
  image_url?: string;
  media_url?: string;
  media_mime?: string;
  media_trimmed?: boolean;
  source?: string;
  source_tier?: string;
  quality_score?: number;
  round?: number;
  map_x?: number;
  map_y?: number;
  citation?: string;
  cite?: string;
  score?: number;
}

export interface ResearchRun {
  run: number;
  sources_examined?: number;
  evidence_indexed?: number;
  images_indexed?: number;
  media_indexed?: number;
  sources_extracted?: number;
  coverage_before?: number;
  coverage_after?: number;
  confidence_before?: number;
  confidence_after?: number;
  new_boxes?: string[];
  conflicts?: string[];
  searches?: { objective: string; queries: string[] }[];
  next_action?: string;
}

export interface Verdict {
  id?: string;
  a_id?: string;
  b_id?: string;
  relation: string;
  explanation: string;
  a_cite: string;
  b_cite: string;
  similarity?: number;
}

export interface AskResponse {
  answer: string;
  sufficient: boolean;
  sources: Evidence[];
}
