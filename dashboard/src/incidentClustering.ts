import type {CrisisReport, ReportPriority} from './api';

const CLUSTER_RADIUS_METRES = 750;
const MIN_TEXT_SIMILARITY = 0.25;

export type IncidentCluster = {
  id: string;
  reports: readonly CrisisReport[];
  center: {lat: number; lng: number} | null;
  independentSenderCount: number;
  reportedCorroborationCount: number;
  priority: ReportPriority;
};

function hasCoordinates(report: CrisisReport): report is CrisisReport & {location: {lat: number; lng: number}} {
  return Number.isFinite(report.location.lat) && Number.isFinite(report.location.lng);
}

function distanceMetres(a: {lat: number; lng: number}, b: {lat: number; lng: number}): number {
  const radians = Math.PI / 180;
  const latitudeDelta = (b.lat - a.lat) * radians;
  const longitudeDelta = (b.lng - a.lng) * radians;
  const latitudeA = a.lat * radians;
  const latitudeB = b.lat * radians;
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(longitudeDelta / 2) ** 2;
  return 6_371_000 * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

function incidentTokens(report: CrisisReport): Set<string> {
  return new Set(
    `${report.payload.text} ${report.payload.needs.join(' ')}`
      .toLocaleLowerCase()
      .match(/[\p{L}\p{N}]+/gu) ?? [],
  );
}

function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  const union = new Set([...a, ...b]);
  if (union.size === 0) return 0;
  let overlap = 0;
  for (const token of a) if (b.has(token)) overlap += 1;
  return overlap / union.size;
}

function clusterCenter(reports: readonly CrisisReport[]): {lat: number; lng: number} | null {
  const located = reports.filter(hasCoordinates);
  if (located.length === 0) return null;
  return {
    lat: located.reduce((total, report) => total + report.location.lat, 0) / located.length,
    lng: located.reduce((total, report) => total + report.location.lng, 0) / located.length,
  };
}

function priorityRank(priority: ReportPriority): number {
  return {critical: 4, high: 3, medium: 2, low: 1, unscored: 0}[priority ?? 'unscored'];
}

function clusterPriority(reports: readonly CrisisReport[]): ReportPriority {
  return reports.reduce<ReportPriority>(
    (highest, report) => (priorityRank(report.priority) > priorityRank(highest) ? report.priority : highest),
    null,
  );
}

function canJoin(cluster: IncidentCluster, candidate: CrisisReport): boolean {
  if (!hasCoordinates(candidate) || cluster.center === null) return false;
  const exemplar = cluster.reports[0];
  if (candidate.type !== exemplar.type) return false;
  if (distanceMetres(cluster.center, candidate.location) > CLUSTER_RADIUS_METRES) return false;
  return jaccardSimilarity(incidentTokens(exemplar), incidentTokens(candidate)) >= MIN_TEXT_SIMILARITY;
}

function makeCluster(reports: readonly CrisisReport[]): IncidentCluster {
  const sortedIds = reports.map(report => report.message_id).sort();
  return {
    id: sortedIds.join(','),
    reports,
    center: clusterCenter(reports),
    independentSenderCount: new Set(reports.map(report => report.sender_pubkey_hash)).size,
    reportedCorroborationCount: Math.max(
      ...reports.map(report => report.verification.corroboration_count),
    ),
    priority: clusterPriority(reports),
  };
}

/**
 * A conservative, deterministic alternative to embedding/DBSCAN clustering.
 * Reports join only when their declared type, nearby location, and token sets
 * agree. This avoids collapsing unrelated emergencies merely because they
 * happened in the same neighbourhood.
 */
export function clusterReports(reports: readonly CrisisReport[]): IncidentCluster[] {
  const ordered = [...reports].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const clusters: IncidentCluster[] = [];

  for (const report of ordered) {
    const index = clusters.findIndex(cluster => canJoin(cluster, report));
    if (index === -1) {
      clusters.push(makeCluster([report]));
      continue;
    }
    clusters[index] = makeCluster([...clusters[index].reports, report]);
  }
  return clusters;
}
