export type LineStatus = "clear" | "needs_look" | "duplicate" | "by_hand";
export type Stage = "intake" | "extraction" | "quote" | "proposal";
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export interface Counts {
  total: number;
  clear: number;
  needsLook: number;
  duplicate: number;
  byHand: number;
}

export interface Job {
  id: string;
  type: string;
  projectId: string | null;
  status: JobStatus;
  attempts: number;
  error: string | null;
  log: string | null;
  note?: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface Project {
  id: string;
  code: string;
  slug: string;
  name: string;
  brand?: string | null;
  jobName?: string | null;
  projectNumber?: string | null;
  location?: string | null;
  state?: string | null;
  architect?: string | null;
  gc?: string | null;
  initiator?: string | null;
  bidDue?: string | null;
  stage: Stage;
  progress: number;
  counts: Counts;
  documentCount: number;
  quoteTotal?: number | null;
  activeJob?: Job | null;
  createdAt: string;
}

export interface BidDocument {
  id: string;
  projectId: string;
  filename: string;
  kind: string;
  pages: number | null;
  bytes: number | null;
  path: string;
  state: string;
  uploadedAt: string;
}

export interface Evidence {
  note?: string | null;
  sheet?: string | null;
  row?: number | null;
  confidence?: number | null;
  sourceFile?: string | null;
  sourcePage?: number | null;
  /** [x0, y0, x1, y1] in PDF points, measured against pageSize. */
  bbox?: number[] | null;
  pageSize?: { width: number; height: number } | null;
}

export interface LineItem {
  id: string;
  projectId: string;
  mark?: string | null;
  description: string;
  size?: string | null;
  qty: number;
  hwSet?: string | null;
  division?: string | null;
  handing?: string | null;
  finish?: string | null;
  fireRating?: string | null;
  frameType?: string | null;
  wallType?: string | null;
  notes?: string | null;
  status: LineStatus;
  confidence?: number | null;
  flags: string[];
  evidence?: Evidence | null;
  duplicateOf?: string | null;
  duplicateReason?: string | null;
  addedByHand: boolean;
  confirmedBy?: string | null;
  confirmedAt?: string | null;
}

export interface LineItemsResponse {
  lineItems: LineItem[];
  counts: {
    all: number;
    needs_look: number;
    duplicate: number;
    by_hand: number;
    clear: number;
  };
}

export interface QuoteLine {
  id: string;
  projectId: string;
  lineKey?: string;
  part?: string | null;
  description: string;
  division?: string | null;
  group?: string | null;
  qty: number;
  cost: number | null;
  margin: number | null;
  sell: number | null;
  extended: number | null;
  basis?: string | null;
  costSource?: string | null;
  costSourceDetail?: string | null;
  multiplier?: number | null;
  multiplierTier?: string | null;
  multiplierEffectiveDate?: string | null;
  priceBookVersion?: string | null;
  sourcePage?: number | null;
  addedByHand: boolean;
  marginOverridden: boolean;
  overrideReason?: string | null;
  priceStatus?: string | null;
  flags: string[];
}

export interface QuoteTotals {
  subtotal: number;
  cost: number;
  margin: number | null;
  taxRate: number;
  tax: number;
  freight: number | null;
  freightNote: string;
  grandTotal: number;
  taxJurisdiction: string | null;
  taxNote: string;
  unpricedLines: number;
  groups: { group: string; line_count: number; subtotal: number }[];
}

export interface QuoteResponse {
  quote: Record<string, unknown> | null;
  groups: { division: string; lines: QuoteLine[]; subtotal: number }[];
  totals: QuoteTotals;
  lineCount: number;
}

export interface Product {
  id: string;
  part: string;
  description: string;
  manufacturer?: string | null;
  division?: string | null;
  cost: number | null;
  listPrice: number | null;
  multiplier: number | null;
  sellAt: number | null;
  availability?: string | null;
  priceBookId?: string | null;
  priceBook?: string | null;
  xref: { manufacturer: string; part: string }[];
  seedSource?: string | null;
  updatedAt?: string | null;
  updatedBy?: string | null;
}

export interface PriceBook {
  id: string;
  vendor: string;
  displayName?: string | null;
  program?: string | null;
  multiplier: number | null;
  categories?: Record<string, number> | null;
  effective: string | null;
  protectedThrough?: string | null;
  lastReviewed?: string | null;
  steward?: string | null;
  account?: string | null;
  note?: string | null;
  kind?: string | null;
  filename?: string | null;
  partCount: number;
  ageDays: number | null;
  stale: boolean;
  undated: boolean;
}

export interface ProposalSection {
  key: string;
  title: string;
  subtotal: number;
  lines: {
    part: string | null;
    qty: number;
    uom: string;
    description: string;
    unitPrice: number | null;
    extPrice: number | null;
    priceStatus?: string | null;
  }[];
}

export interface ProposalResponse {
  proposal: {
    proposalNo: string;
    date: string;
    validityDays: number;
    customer: Record<string, string | null>;
    salesRep: Record<string, string | null>;
    estimator: Record<string, string | null>;
    markup: number;
    exclusions: string[];
    signoff: { role: string; by: string; at: string; state: string }[];
    sentAt: string | null;
  };
  project: Project;
  sections: ProposalSection[];
  totals: QuoteTotals & { markup: number };
  readiness: {
    flaggedLineItems: number;
    unpricedQuoteLines: number;
    blocking: boolean;
    note: string;
  };
}
