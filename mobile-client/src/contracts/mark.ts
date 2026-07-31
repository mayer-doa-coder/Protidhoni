export type MarkCategory =
  | 'HAZARD'
  | 'SAFE_ROUTE'
  | 'SHELTER'
  | 'RESOURCE'
  | 'OTHER';

/**
 * A peer-visible pin on the offline map (Protidhoni_Roadmap.md's map-based
 * situational picture, extended to work entirely mesh-local with no backend
 * round trip). Deliberately a separate, smaller envelope from CrisisReport —
 * marks never reach the backend, so they carry no sync_status/verification
 * workflow, only what's needed to place, sign, and relay a pin peer-to-peer.
 */
export interface MapMark {
  schema_version: '1.0.0';
  mark_id: string;
  sender_pubkey: string;
  sender_pubkey_hash: string;
  created_at: string;
  lat: number;
  lng: number;
  category: MarkCategory;
  label: string;
  signature: {algorithm: 'Ed25519'; value: string};
  ttl_hops: number;
  relay_path: string[];
}
