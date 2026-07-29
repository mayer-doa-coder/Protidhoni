import {MapContainer, TileLayer} from 'react-leaflet';
import {useEffect, useState} from 'react';

import {getApiHealth, type ApiHealth} from './api';
import 'leaflet/dist/leaflet.css';
import './styles.css';

const dhaka: [number, number] = [23.8103, 90.4125];

export default function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getApiHealth(controller.signal).then(setHealth).catch(errorValue => {
      if (errorValue.name !== 'AbortError') setError(errorValue.message);
    });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Protidhoni · responder view</p>
          <h1>Crisis reports, ready for verified data</h1>
        </div>
        <p className={health ? 'healthy' : 'unhealthy'}>
          {health ? `Backend ${health.status}` : error ?? 'Checking backend…'}
        </p>
      </header>
      <section className="map-frame" aria-label="Dhaka map; reports will appear in Phase 1">
        <MapContainer center={dhaka} zoom={12} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </MapContainer>
        <aside>
          <strong>Phase 0 boundary</strong>
          <span>The map and backend-health connection are live. Report pins, filtering, and verification workflow begin in Phase 1/2 once ingestion exists.</span>
        </aside>
      </section>
    </main>
  );
}
