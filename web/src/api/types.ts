export const SECTION_META = [
  { key: "done", label: "今日完成" },
  { key: "doing", label: "进行中" },
  { key: "risk", label: "风险与阻塞" },
  { key: "plan", label: "明日计划" },
] as const;

export type SectionKey = (typeof SECTION_META)[number]["key"];

export interface ReportItem {
  id: number;
  content: string;
  source_event_ids: number[];
  confidence: number;
  confirmed: boolean;
}

export type ReportStatus = "draft" | "submitted" | "pushed" | "withdrawn";

export interface ReportPayload {
  id: number;
  member_id: number;
  report_date: string;
  status: ReportStatus;
  version: number;
  sections: Record<SectionKey, ReportItem[]>;
}

export interface TeamInfo {
  id: number;
  name: string;
  role: string;
  is_lead: boolean;
}

export interface Me {
  id: number;
  name: string;
  email: string | null;
  teams: TeamInfo[];
}

export interface GenerateResult {
  status: string;
  report_id: number | null;
  events: number;
  inserted: number;
  pushed: boolean;
  degraded: boolean;
}

export interface Digest {
  team_id: number;
  report_date: string;
  content_md: string;
  member_count: number;
  submitted_count: number;
}
