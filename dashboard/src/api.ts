export type ApiHealth = {service: string; status: 'ok'; version: string};
export type ReportType =
  | 'SOS'
  | 'MEDICAL_NEED'
  | 'RESOURCE_NEED'
  | 'SAFETY_STATUS'
  | 'SHELTER_INFO'
  | 'HAZARD_UPDATE'
  | 'SAFE_ROUTE'
  | 'INSTRUCTION';
export type ReportPriority = 'critical' | 'high' | 'medium' | 'low' | null;
export type VerificationStatus = 'unverified' | 'corroborated' | 'verified' | 'disputed';

export interface CrisisReport {
  schema_version: '1.0.0';
  message_id: string;
  type: ReportType;
  sender_pubkey_hash: string;
  created_at: string;
  language: 'bn' | 'en';
  location: {
    lat: number | null;
    lng: number | null;
    accuracy_m: number | null;
    source: 'gps' | 'manual' | 'none';
  };
  payload: {
    text: string;
    people_count: number | null;
    needs: string[];
    attachment_ref: string | null;
  };
  priority: ReportPriority;
  ttl_hops: number;
  relay_path: string[];
  sync_status: 'local' | 'relayed' | 'synced';
  verification: {
    status: VerificationStatus;
    corroboration_count: number;
  };
}

export interface ReportCollection {
  reports: CrisisReport[];
  next_since: string | null;
}

export type VerificationUpdate = {
  status: VerificationStatus;
  responder_note?: string;
};

export type ReportTranslation = {
  message_id: string;
  source_language: 'bn' | 'en';
  target_language: 'bn' | 'en';
  text: string;
  provider: string;
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '');

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {signal, cache: 'no-store'});
  if (!response.ok) throw new Error(`Backend request failed (${response.status}).`);
  return response.json() as Promise<T>;
}

export function getApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  return getJson<ApiHealth>('/health', signal);
}

export async function getReports(signal?: AbortSignal): Promise<ReportCollection> {
  const collection = await getJson<ReportCollection>('/reports?limit=200', signal);
  if (!Array.isArray(collection.reports)) {
    throw new Error('Backend returned an invalid report collection.');
  }
  return collection;
}

export async function updateReportVerification(
  messageId: string,
  update: VerificationUpdate,
  responderToken: string,
): Promise<CrisisReport> {
  const token = responderToken.trim();
  if (!token) throw new Error('Enter the responder token before updating verification.');
  const note = update.responder_note?.trim();
  if (note && note.length > 1000) throw new Error('Responder notes must be 1,000 characters or fewer.');

  const response = await fetch(`${apiBaseUrl}/reports/${encodeURIComponent(messageId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-Responder-Token': token,
    },
    body: JSON.stringify({
      status: update.status,
      ...(note ? {responder_note: note} : {}),
    }),
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`Verification update failed (${response.status}).`);
  return response.json() as Promise<CrisisReport>;
}

export async function translateReport(
  messageId: string,
  targetLanguage: 'bn' | 'en',
  responderToken: string,
): Promise<ReportTranslation> {
  const token = responderToken.trim();
  if (!token) throw new Error('Enter the responder token before requesting a translation.');

  const response = await fetch(`${apiBaseUrl}/translations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Responder-Token': token,
    },
    body: JSON.stringify({message_id: messageId, target_language: targetLanguage}),
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`Translation request failed (${response.status}).`);
  return response.json() as Promise<ReportTranslation>;
}
