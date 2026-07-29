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
export type SyncStatus = 'local' | 'relayed' | 'synced';

/** Mirrors contracts/message-schema.json. Update only via an agreed contract version change. */
export interface CrisisReport {
  schema_version: '1.0.0';
  message_id: string;
  type: ReportType;
  sender_pubkey: string;
  sender_pubkey_hash: string;
  created_at: string;
  language: 'bn' | 'en';
  location: {lat: number | null; lng: number | null; accuracy_m: number | null; source: 'gps' | 'manual' | 'none'};
  payload: {text: string; people_count: number | null; needs: string[]; attachment_ref: string | null};
  priority: ReportPriority;
  ttl_hops: number;
  signature: {algorithm: 'Ed25519'; value: string};
  relay_path: string[];
  sync_status: SyncStatus;
  verification: {status: 'unverified' | 'corroborated' | 'verified' | 'disputed'; corroboration_count: number};
}
