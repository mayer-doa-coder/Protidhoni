import {useCallback, useEffect, useMemo, useState} from 'react';
import {CircleMarker, MapContainer, Popup, TileLayer, useMap} from 'react-leaflet';

import {getApiHealth, getReports, type ApiHealth, type CrisisReport} from './api';
import {hasMappableLocation, priorityLabel, reportPinColour} from './reportPresentation';
import 'leaflet/dist/leaflet.css';
import './styles.css';

const dhaka: [number, number] = [23.8103, 90.4125];
const refreshIntervalMs = 15_000;

type MappableReport = CrisisReport & {location: {lat: number; lng: number}};

function FitReportBounds({reports}: {reports: MappableReport[]}) {
  const map = useMap();

  useEffect(() => {
    if (reports.length === 0) return;
    map.fitBounds(
      reports.map(report => [report.location.lat, report.location.lng]),
      {padding: [36, 36], maxZoom: 14},
    );
  }, [map, reports]);

  return null;
}

function ReportPopup({report}: {report: MappableReport}) {
  return (
    <article className="report-popup">
      <div className="popup-heading">
        <strong>{report.type.replaceAll('_', ' ')}</strong>
        <span className="priority-chip" style={{backgroundColor: reportPinColour(report.priority)}}>
          {priorityLabel(report.priority)}
        </span>
      </div>
      <p lang={report.language}>{report.payload.text}</p>
      <dl>
        <div>
          <dt>People</dt>
          <dd>{report.payload.people_count ?? 'Not stated'}</dd>
        </div>
        <div>
          <dt>Needs</dt>
          <dd>{report.payload.needs.join(', ') || 'Not stated'}</dd>
        </div>
        <div>
          <dt>Verification</dt>
          <dd>{report.verification.status}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{new Date(report.created_at).toLocaleString()}</dd>
        </div>
      </dl>
    </article>
  );
}

export default function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [reports, setReports] = useState<CrisisReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [healthResult, reportResult] = await Promise.all([
        getApiHealth(signal),
        getReports(signal),
      ]);
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

  const mappableReports = useMemo(
    () => reports.filter(hasMappableLocation),
    [reports],
  );
  const missingLocationCount = reports.length - mappableReports.length;

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Protidhoni · responder view</p>
          <h1>Incoming crisis reports</h1>
          <p className="lede">Live map of signed reports synced through the offline relay network.</p>
        </div>
        <div className="connection-panel">
          <p className={health && !error ? 'healthy' : 'unhealthy'}>
            {error ?? (health ? `Backend ${health.status}` : 'Checking backend…')}
          </p>
          <button type="button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <section className="summary-grid" aria-label="Report summary">
        <div><strong>{reports.length}</strong><span>Total reports</span></div>
        <div><strong>{mappableReports.length}</strong><span>Visible pins</span></div>
        <div><strong>{missingLocationCount}</strong><span>Without location</span></div>
        <div><strong>{reports.filter(report => report.priority === 'critical').length}</strong><span>Critical</span></div>
      </section>

      <section className="map-frame" aria-label="Map of crisis report pins">
        <MapContainer center={dhaka} zoom={12} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitReportBounds reports={mappableReports} />
          {mappableReports.map(report => (
            <CircleMarker
              key={report.message_id}
              center={[report.location.lat, report.location.lng]}
              radius={10}
              pathOptions={{
                color: '#ffffff',
                fillColor: reportPinColour(report.priority),
                fillOpacity: 0.95,
                weight: 2,
              }}>
              <Popup><ReportPopup report={report} /></Popup>
            </CircleMarker>
          ))}
        </MapContainer>

        {mappableReports.length === 0 && !loading && !error && (
          <div className="empty-state">No reports with coordinates have arrived yet.</div>
        )}

        <aside className="legend">
          <strong>Priority</strong>
          {(['critical', 'high', 'medium', 'low', null] as const).map(priority => (
            <span key={priority ?? 'unscored'}>
              <i style={{backgroundColor: reportPinColour(priority)}} />
              {priorityLabel(priority)}
            </span>
          ))}
          <small>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Waiting for data'}</small>
        </aside>
      </section>
    </main>
  );
}
