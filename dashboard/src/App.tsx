import {useCallback, useEffect, useMemo, useState} from 'react';
import {CircleMarker, MapContainer, Popup, TileLayer, useMap} from 'react-leaflet';

import {
  getApiHealth,
  getReports,
  translateReport,
  updateReportVerification,
  type ApiHealth,
  type CrisisReport,
  type ReportPriority,
  type ReportTranslation,
  type ReportType,
  type VerificationStatus,
} from './api';
import {clusterReports, type IncidentCluster} from './incidentClustering';
import {
  allowedVerificationUpdates,
  matchesFilters,
  priorityLabel,
  reportChannel,
  reportPinColour,
  ALL_FILTERS,
  CHANNEL_DESCRIPTIONS,
  CHANNEL_LABELS,
  type ReportChannel,
  type ReportFilters,
} from './reportPresentation';
import 'leaflet/dist/leaflet.css';
import './styles.css';

const dhaka: [number, number] = [23.8103, 90.4125];
const refreshIntervalMs = 15_000;
const reportTypes: readonly ReportType[] = [
  'SOS',
  'MEDICAL_NEED',
  'RESOURCE_NEED',
  'SAFETY_STATUS',
  'SHELTER_INFO',
  'HAZARD_UPDATE',
  'SAFE_ROUTE',
  'INSTRUCTION',
];
const verificationStatuses: readonly VerificationStatus[] = [
  'unverified',
  'corroborated',
  'verified',
  'disputed',
];
const priorities: readonly (Exclude<ReportPriority, null> | 'unscored')[] = [
  'critical',
  'high',
  'medium',
  'low',
  'unscored',
];

const channels: readonly ReportChannel[] = ['gateway', 'device'];

type MappableCluster = IncidentCluster & {center: {lat: number; lng: number}};
type Filters = ReportFilters;

function FitClusterBounds({clusters}: {clusters: MappableCluster[]}) {
  const map = useMap();

  useEffect(() => {
    if (clusters.length === 0) return;
    map.fitBounds(
      clusters.map(cluster => [cluster.center.lat, cluster.center.lng]),
      {padding: [36, 36], maxZoom: 14},
    );
  }, [clusters, map]);

  return null;
}

function VerificationControls({
  report,
  responderToken,
  submitting,
  onUpdate,
}: {
  report: CrisisReport;
  responderToken: string;
  submitting: boolean;
  onUpdate: (status: VerificationStatus, note: string) => Promise<void>;
}) {
  const allowed = allowedVerificationUpdates(report.verification.status);
  const [status, setStatus] = useState<VerificationStatus>(allowed[0] ?? report.verification.status);
  const [note, setNote] = useState('');

  if (allowed.length === 0) {
    return <p className="terminal-state">Verification is terminal: {report.verification.status}.</p>;
  }

  return (
    <form
      className="verification-form"
      onSubmit={event => {
        event.preventDefault();
        void onUpdate(status, note);
      }}>
      <label>
        Verification
        <select value={status} onChange={event => setStatus(event.target.value as VerificationStatus)}>
          {allowed.map(option => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
      <label>
        Responder note (optional)
        <textarea
          value={note}
          onChange={event => setNote(event.target.value)}
          maxLength={1000}
          rows={2}
        />
      </label>
      <button type="submit" disabled={submitting || !responderToken.trim()}>
        {submitting ? 'Updating…' : 'Update verification'}
      </button>
    </form>
  );
}

function ReportDetails({
  report,
  gatewayPubkeyHash,
  responderToken,
  submitting,
  translation,
  translating,
  onUpdate,
  onTranslate,
}: {
  report: CrisisReport;
  gatewayPubkeyHash: string | null | undefined;
  responderToken: string;
  submitting: boolean;
  translation: ReportTranslation | undefined;
  translating: boolean;
  onUpdate: (report: CrisisReport, status: VerificationStatus, note: string) => Promise<void>;
  onTranslate: (report: CrisisReport, targetLanguage: 'bn' | 'en') => Promise<void>;
}) {
  const targetLanguage = report.language === 'bn' ? 'en' : 'bn';
  const targetLanguageName = targetLanguage === 'bn' ? 'Bangla' : 'English';
  const channel = reportChannel(report, gatewayPubkeyHash);

  return (
    <article className="report-details">
      <div className="popup-heading">
        <strong>{report.type.replaceAll('_', ' ')}</strong>
        <span className="priority-chip" style={{backgroundColor: reportPinColour(report.priority)}}>
          {priorityLabel(report.priority)}
        </span>
        <span className={`channel-chip channel-${channel}`} title={CHANNEL_DESCRIPTIONS[channel]}>
          {CHANNEL_LABELS[channel]}
        </span>
      </div>
      <p className="original-label">Original ({report.language === 'bn' ? 'Bangla' : 'English'})</p>
      <p lang={report.language}>{report.payload.text}</p>
      {translation ? (
        <section className="translation-result">
          <p className="translation-label">Translation ({translation.target_language === 'bn' ? 'Bangla' : 'English'})</p>
          <p lang={translation.target_language}>{translation.text}</p>
        </section>
      ) : (
        <button
          className="translation-button"
          type="button"
          disabled={translating || !responderToken.trim()}
          onClick={() => void onTranslate(report, targetLanguage)}>
          {translating ? 'Translating…' : `Translate to ${targetLanguageName}`}
        </button>
      )}
      <dl>
        <div><dt>People</dt><dd>{report.payload.people_count ?? 'Not stated'}</dd></div>
        <div><dt>Needs</dt><dd>{report.payload.needs.join(', ') || 'Not stated'}</dd></div>
        <div><dt>Verification</dt><dd>{report.verification.status}</dd></div>
        <div><dt>Server corroboration</dt><dd>{report.verification.corroboration_count}</dd></div>
        <div><dt>Received</dt><dd>{new Date(report.created_at).toLocaleString()}</dd></div>
      </dl>
      <VerificationControls
        key={`${report.message_id}:${report.verification.status}`}
        report={report}
        responderToken={responderToken}
        submitting={submitting}
        onUpdate={(status, note) => onUpdate(report, status, note)}
      />
    </article>
  );
}

function ClusterPopup({
  cluster,
  gatewayPubkeyHash,
  responderToken,
  updatingIds,
  translations,
  translatingIds,
  onUpdate,
  onTranslate,
}: {
  cluster: IncidentCluster;
  gatewayPubkeyHash: string | null | undefined;
  responderToken: string;
  updatingIds: ReadonlySet<string>;
  translations: Readonly<Record<string, ReportTranslation>>;
  translatingIds: ReadonlySet<string>;
  onUpdate: (report: CrisisReport, status: VerificationStatus, note: string) => Promise<void>;
  onTranslate: (report: CrisisReport, targetLanguage: 'bn' | 'en') => Promise<void>;
}) {
  return (
    <section className="report-popup">
      <div className="cluster-summary">
        <strong>{cluster.reports.length} related report{cluster.reports.length === 1 ? '' : 's'}</strong>
        <span>{cluster.independentSenderCount} independent sender{cluster.independentSenderCount === 1 ? '' : 's'}</span>
        <span>Highest server corroboration: {cluster.reportedCorroborationCount}</span>
      </div>
      {cluster.reports.map(report => (
        <ReportDetails
          key={report.message_id}
          report={report}
          gatewayPubkeyHash={gatewayPubkeyHash}
          responderToken={responderToken}
          submitting={updatingIds.has(report.message_id)}
          translation={translations[report.message_id]}
          translating={translatingIds.has(report.message_id)}
          onUpdate={onUpdate}
          onTranslate={onTranslate}
        />
      ))}
    </section>
  );
}

export default function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [reports, setReports] = useState<CrisisReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [responderToken, setResponderToken] = useState('');
  const [updatingIds, setUpdatingIds] = useState<ReadonlySet<string>>(new Set());
  const [translations, setTranslations] = useState<Readonly<Record<string, ReportTranslation>>>({});
  const [translatingIds, setTranslatingIds] = useState<ReadonlySet<string>>(new Set());
  const [filters, setFilters] = useState<Filters>(ALL_FILTERS);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [healthResult, reportResult] = await Promise.all([getApiHealth(signal), getReports(signal)]);
      setHealth(healthResult);
      setReports(reportResult.reports);
      setLastUpdated(new Date());
      setError(null);
    } catch (errorValue) {
      if (errorValue instanceof DOMException && errorValue.name === 'AbortError') return;
      setError(errorValue instanceof Error ? errorValue.message : 'Unable to load reports.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const interval = window.setInterval(() => void load(controller.signal), refreshIntervalMs);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [load]);

  const gatewayPubkeyHash = health?.gateway_pubkey_hash ?? null;

  useEffect(() => {
    if (gatewayPubkeyHash) return;
    setFilters(current => current.channel === 'all' ? current : {...current, channel: 'all'});
  }, [gatewayPubkeyHash]);

  const filteredReports = useMemo(
    () => reports.filter(report => matchesFilters(report, filters, gatewayPubkeyHash)),
    [filters, gatewayPubkeyHash, reports],
  );
  const gatewayReportCount = useMemo(
    () => reports.filter(report => reportChannel(report, gatewayPubkeyHash) === 'gateway').length,
    [gatewayPubkeyHash, reports],
  );
  const clusters = useMemo(() => clusterReports(filteredReports), [filteredReports]);
  const mappableClusters = useMemo(
    () => clusters.filter((cluster): cluster is MappableCluster => cluster.center !== null),
    [clusters],
  );
  const missingLocationCount = filteredReports.length - mappableClusters.reduce(
    (total, cluster) => total + cluster.reports.length,
    0,
  );

  const updateVerification = useCallback(async (
    report: CrisisReport,
    status: VerificationStatus,
    note: string,
  ) => {
    setActionError(null);
    setUpdatingIds(current => new Set(current).add(report.message_id));
    try {
      const updated = await updateReportVerification(report.message_id, {status, responder_note: note}, responderToken);
      setReports(current => current.map(item => item.message_id === updated.message_id ? updated : item));
    } catch (errorValue) {
      setActionError(errorValue instanceof Error ? errorValue.message : 'Verification update failed.');
    } finally {
      setUpdatingIds(current => {
        const next = new Set(current);
        next.delete(report.message_id);
        return next;
      });
    }
  }, [responderToken]);

  const requestTranslation = useCallback(async (
    report: CrisisReport,
    targetLanguage: 'bn' | 'en',
  ) => {
    setActionError(null);
    setTranslatingIds(current => new Set(current).add(report.message_id));
    try {
      const translation = await translateReport(report.message_id, targetLanguage, responderToken);
      if (translation.message_id !== report.message_id || translation.target_language !== targetLanguage) {
        throw new Error('Backend returned a translation for a different report or language.');
      }
      setTranslations(current => ({...current, [report.message_id]: translation}));
    } catch (errorValue) {
      setActionError(errorValue instanceof Error ? errorValue.message : 'Translation request failed.');
    } finally {
      setTranslatingIds(current => {
        const next = new Set(current);
        next.delete(report.message_id);
        return next;
      });
    }
  }, [responderToken]);

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Protidhoni · responder view</p>
          <h1>Incoming crisis reports</h1>
          <p className="lede">Live incident clusters from signed reports synced through the offline relay network.</p>
        </div>
        <div className="connection-panel">
          <p className={health && !error ? 'healthy' : 'unhealthy'}>
            {error ?? (health ? `Backend ${health.status}` : 'Checking backend…')}
          </p>
          <label className="token-input">
            Responder token
            <input
              type="password"
              autoComplete="off"
              value={responderToken}
              onChange={event => setResponderToken(event.target.value)}
              placeholder="Required only to update verification"
            />
          </label>
          <button type="button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <section className="filters" aria-label="Report filters">
        <label>Type<select value={filters.type} onChange={event => setFilters(current => ({...current, type: event.target.value as Filters['type']}))}>
          <option value="all">All types</option>{reportTypes.map(type => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></label>
        <label>Verification<select value={filters.verification} onChange={event => setFilters(current => ({...current, verification: event.target.value as Filters['verification']}))}>
          <option value="all">All states</option>{verificationStatuses.map(status => <option key={status} value={status}>{status}</option>)}</select></label>
        <label>Priority<select value={filters.priority} onChange={event => setFilters(current => ({...current, priority: event.target.value as Filters['priority']}))}>
          <option value="all">All priorities</option>{priorities.map(priority => <option key={priority} value={priority}>{priority}</option>)}</select></label>
        <label>Channel<select
          value={filters.channel}
          disabled={!gatewayPubkeyHash}
          title={gatewayPubkeyHash
            ? 'Filter by the signing identity that attested the report.'
            : 'Gateway attribution is unavailable because the backend published no gateway identity.'}
          onChange={event => setFilters(current => ({...current, channel: event.target.value as Filters['channel']}))}>
          <option value="all">All channels</option>{channels.map(channel => <option key={channel} value={channel}>{CHANNEL_LABELS[channel]}</option>)}</select></label>
      </section>
      {actionError && <p className="action-error" role="alert">{actionError}</p>}

      <section className="summary-grid" aria-label="Report summary">
        <div><strong>{filteredReports.length}</strong><span>Filtered reports</span></div>
        <div><strong>{clusters.length}</strong><span>Incident clusters</span></div>
        <div><strong>{mappableClusters.length}</strong><span>Visible pins</span></div>
        <div><strong>{missingLocationCount}</strong><span>Without location</span></div>
        {gatewayPubkeyHash && (
          <div title={CHANNEL_DESCRIPTIONS.gateway}>
            <strong>{gatewayReportCount}</strong><span>Gateway-attested</span>
          </div>
        )}
      </section>

      <section className="map-frame" aria-label="Map of crisis report clusters">
        <MapContainer center={dhaka} zoom={12} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitClusterBounds clusters={mappableClusters} />
          {mappableClusters.map(cluster => (
            <CircleMarker
              key={cluster.id}
              center={[cluster.center.lat, cluster.center.lng]}
              radius={Math.min(10 + (cluster.reports.length - 1) * 3, 22)}
              pathOptions={{color: '#ffffff', fillColor: reportPinColour(cluster.priority), fillOpacity: 0.95, weight: 2}}>
              <Popup><ClusterPopup cluster={cluster} gatewayPubkeyHash={gatewayPubkeyHash} responderToken={responderToken} updatingIds={updatingIds} translations={translations} translatingIds={translatingIds} onUpdate={updateVerification} onTranslate={requestTranslation} /></Popup>
            </CircleMarker>
          ))}
        </MapContainer>
        {mappableClusters.length === 0 && !loading && !error && (
          <div className="empty-state">No filtered reports with coordinates have arrived yet.</div>
        )}
        <aside className="legend">
          <strong>Priority</strong>
          {(['critical', 'high', 'medium', 'low', null] as const).map(priority => (
            <span key={priority ?? 'unscored'}><i style={{backgroundColor: reportPinColour(priority)}} />{priorityLabel(priority)}</span>
          ))}
          <small>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Waiting for data'}</small>
        </aside>
      </section>
    </main>
  );
}
