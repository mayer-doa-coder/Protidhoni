import type {
  CrisisReport,
  ReportPriority,
  ReportType,
  VerificationStatus,
} from './api';

const pinColours: Record<Exclude<ReportPriority, null> | 'unscored', string> = {
  critical: '#b91c1c',
  high: '#ea580c',
  medium: '#2563eb',
  low: '#15803d',
  unscored: '#64748b',
};

export function reportPinColour(priority: ReportPriority): string {
  return pinColours[priority ?? 'unscored'];
}

export function hasMappableLocation(
  report: CrisisReport,
): report is CrisisReport & {location: {lat: number; lng: number}} {
  return Number.isFinite(report.location.lat) && Number.isFinite(report.location.lng);
}

export function priorityLabel(priority: ReportPriority): string {
  return priority ?? 'unscored';
}

export function allowedVerificationUpdates(status: VerificationStatus): VerificationStatus[] {
  if (status === 'unverified') return ['corroborated', 'verified', 'disputed'];
  if (status === 'corroborated') return ['verified', 'disputed'];
  return [];
}

export type ReportChannel = 'gateway' | 'device' | 'unknown';

/**
 * Which signing identity attested a report.
 *
 * A feature phone cannot sign anything, so the SMS/USSD gateway signs on its
 * behalf and every report from that channel carries the gateway's own
 * `sender_pubkey_hash`. Comparing against the hash the backend publishes on
 * `GET /health` is therefore the whole detection rule — no schema field was
 * added for this.
 *
 * The frozen report schema does not record whether the gateway received a
 * report through SMS or USSD. It also cannot prove a non-matching signer is a
 * device when the backend does not publish its current gateway identity.
 */
export function reportChannel(
  report: CrisisReport,
  gatewayPubkeyHash: string | null | undefined,
): ReportChannel {
  if (!gatewayPubkeyHash) return 'unknown';
  return report.sender_pubkey_hash === gatewayPubkeyHash ? 'gateway' : 'device';
}

export function isGatewayReport(
  report: CrisisReport,
  gatewayPubkeyHash: string | null | undefined,
): boolean {
  return reportChannel(report, gatewayPubkeyHash) === 'gateway';
}

/**
 * These labels describe only the signer that can be verified from the report.
 * They do not claim the exact gateway adapter or a verified human sender.
 */
export const CHANNEL_LABELS: Record<ReportChannel, string> = {
  gateway: 'Gateway-attested',
  device: 'Device-signed',
  unknown: 'Signer unknown',
};

export const CHANNEL_DESCRIPTIONS: Record<ReportChannel, string> = {
  gateway:
    'Signed by the currently configured SMS/USSD gateway. The report does not identify ' +
    'the upstream adapter or authenticate the human sender.',
  device:
    'Signed by an identity other than the currently configured gateway, normally an app device.',
  unknown:
    'The backend did not publish a gateway identity, so this report cannot be attributed safely.',
};

export type ReportFilters = {
  type: ReportType | 'all';
  verification: VerificationStatus | 'all';
  priority: Exclude<ReportPriority, null> | 'unscored' | 'all';
  channel: ReportChannel | 'all';
};

export const ALL_FILTERS: ReportFilters = {
  type: 'all',
  verification: 'all',
  priority: 'all',
  channel: 'all',
};

/**
 * Whether one report survives the responder's active filters.
 *
 * Extracted from the view so the composition is directly testable: a responder
 * triaging an incident must be able to trust that narrowing by channel does not
 * silently drop reports that match, or keep ones that do not.
 */
export function matchesFilters(
  report: CrisisReport,
  filters: ReportFilters,
  gatewayPubkeyHash: string | null | undefined,
): boolean {
  if (filters.type !== 'all' && report.type !== filters.type) return false;
  if (filters.verification !== 'all' && report.verification.status !== filters.verification) {
    return false;
  }
  if (filters.priority !== 'all') {
    const matchesPriority =
      filters.priority === 'unscored'
        ? report.priority === null
        : report.priority === filters.priority;
    if (!matchesPriority) return false;
  }
  if (filters.channel !== 'all' && reportChannel(report, gatewayPubkeyHash) !== filters.channel) {
    return false;
  }
  return true;
}
