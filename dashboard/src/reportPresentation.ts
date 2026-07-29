import type {CrisisReport, ReportPriority, VerificationStatus} from './api';

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
