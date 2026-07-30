import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { CrisisReport } from './src/contracts/report';
import { getAppDatabase } from './src/db/appDatabase';
import { startMeshRelay, type MeshRelayController } from './src/mesh/relay';
import {
  useNearbySession,
  type NearbySession,
} from './src/mesh/useNearbySession';
import { MyReportsScreen } from './src/screens/MyReportsScreen';
import { ReportFormScreen } from './src/screens/ReportFormScreen';
import { startAutoSync } from './src/sync/sync';
import {
  defaultBackendOrigin,
  loadBackendOrigin,
  saveBackendOrigin,
} from './src/config/backend';

type Tab = 'create' | 'reports' | 'mesh';

function TabButton({
  label,
  active,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      testID={testID}
      style={[styles.tabButton, active && styles.tabButtonActive]}
    >
      <Text style={active ? styles.tabLabelActive : styles.tabLabel}>
        {label}
      </Text>
    </Pressable>
  );
}

function MeshScreen({
  apiBaseUrl,
  onApiBaseUrlChange,
  nearby,
}: {
  apiBaseUrl: string;
  onApiBaseUrlChange: (value: string) => void;
  nearby: NearbySession;
}) {
  const [backendDraft, setBackendDraft] = useState(apiBaseUrl);
  const [backendFeedback, setBackendFeedback] = useState('');
  const endpointList = useMemo(
    () => Object.entries(nearby.endpoints),
    [nearby.endpoints],
  );
  const connectedPeerList = useMemo(
    () => Object.entries(nearby.connectedPeers),
    [nearby.connectedPeers],
  );
  const pendingRequestList = useMemo(
    () => Object.entries(nearby.pendingRequests),
    [nearby.pendingRequests],
  );

  useEffect(() => setBackendDraft(apiBaseUrl), [apiBaseUrl]);

  const saveBackend = async () => {
    try {
      const saved = await saveBackendOrigin(backendDraft);
      onApiBaseUrlChange(saved);
      setBackendFeedback('Saved. Queue sync now uses this backend.');
    } catch (error) {
      setBackendFeedback(
        error instanceof Error ? error.message : 'Could not save the backend URL.',
      );
    }
  };

  const toggleNearby = async () => {
    if (nearby.active) await nearby.stop();
    else await nearby.start();
  };

  return (
    <ScrollView contentContainerStyle={styles.meshPage} keyboardShouldPersistTaps="handled">
      <View style={styles.card}>
        <Text style={styles.title}>Protidhoni</Text>
        <Text style={styles.subtitle}>Offline peer mesh</Text>
        <Text style={styles.detail}>
          Advertises and discovers nearby devices, and requests a connection to
          each one found. Every incoming connection request waits below for you
          to accept or decline before any payload is exchanged.
        </Text>
        <Text style={styles.heading}>Backend connection</Text>
        <Text style={styles.detail}>
          Emulator: http://10.0.2.2:8000. On a real phone, use this computer&apos;s
          LAN IP.
        </Text>
        <TextInput
          accessibilityLabel="Backend URL"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          onChangeText={setBackendDraft}
          placeholder="http://192.168.1.20:8000"
          style={styles.backendInput}
          testID="backend-url"
          value={backendDraft}
        />
        <Pressable
          onPress={saveBackend}
          style={styles.secondaryButton}
          testID="save-backend-url"
        >
          <Text style={styles.buttonText}>Save backend URL</Text>
        </Pressable>
        {backendFeedback ? (
          <Text style={styles.status}>{backendFeedback}</Text>
        ) : null}
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
            void toggleNearby();
          }}
          disabled={nearby.starting}
          style={[styles.button, nearby.starting && styles.buttonDisabled]}
        >
          <Text style={styles.buttonText}>
            {nearby.starting
              ? 'Starting nearby…'
              : nearby.active
                ? 'Stop discovery'
                : 'Start nearby discovery'}
          </Text>
        </Pressable>
        <Text style={styles.status} testID="nearby-session-detail">
          {nearby.statusMessage}
        </Text>
        {pendingRequestList.length > 0 && (
          <View style={styles.requestSection}>
            <Text style={styles.heading}>
              Connection requests ({pendingRequestList.length})
            </Text>
            {pendingRequestList.map(([endpointId, request]) => (
              <View key={endpointId} style={styles.requestRow}>
                <Text style={styles.requestName}>
                  Connect with {request.name}?
                </Text>
                <Text style={styles.authDigits}>
                  Confirm digits: {request.authenticationDigits}
                </Text>
                <View style={styles.requestActions}>
                  <Pressable
                    accessibilityRole="button"
                    testID={`accept-${endpointId}`}
                    onPress={() => {
                      // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
                      void nearby.respond(endpointId, true);
                    }}
                    style={[styles.requestButton, styles.acceptButton]}
                  >
                    <Text style={styles.requestButtonText}>Accept</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    testID={`decline-${endpointId}`}
                    onPress={() => {
                      // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
                      void nearby.respond(endpointId, false);
                    }}
                    style={[styles.requestButton, styles.declineButton]}
                  >
                    <Text style={styles.requestButtonText}>Decline</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </View>
        )}
        <Text style={styles.heading} testID="connected-peer-count">
          Connected peers ({connectedPeerList.length})
        </Text>
        {connectedPeerList.length === 0 ? (
          <Text style={styles.status}>No active peer connections.</Text>
        ) : (
          connectedPeerList.map(([id, name]) => (
            <Text key={id} style={styles.connectedPeer}>
              ● {name}
            </Text>
          ))
        )}
        <Text style={styles.heading}>
          Devices in range ({endpointList.length})
        </Text>
        {endpointList.map(([id, name]) => (
          <Text key={id} style={styles.endpoint}>
            {name}
          </Text>
        ))}
      </View>
    </ScrollView>
  );
}

function App() {
  const [tab, setTab] = useState<Tab>('create');
  const [apiBaseUrl, setApiBaseUrl] = useState(defaultBackendOrigin);
  const [reportsRevision, setReportsRevision] = useState(0);
  const nearby = useNearbySession();
  const relayRef = useRef<MeshRelayController | null>(null);
  const relayReadyRef = useRef<Promise<MeshRelayController | null> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const ready = getAppDatabase().then(db => {
      if (cancelled) return null;
      const relay = startMeshRelay(db, () => {
        setReportsRevision(current => current + 1);
      });
      relayRef.current = relay;
      return relay;
    });
    relayReadyRef.current = ready;

    return () => {
      cancelled = true;
      relayRef.current?.stop();
      relayRef.current = null;
      relayReadyRef.current = null;
    };
  }, []);

  const relayNewReport = useCallback(
    async (report: CrisisReport): Promise<number> => {
      const relay = relayRef.current ?? (await relayReadyRef.current);
      return relay?.relayReport(report) ?? 0;
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line no-void -- effect callbacks cannot be async
    void loadBackendOrigin(apiBaseUrl).then(stored => {
      if (!cancelled && stored !== apiBaseUrl) setApiBaseUrl(stored);
    });
    return () => {
      cancelled = true;
    };
    // Load the persisted override once; later changes already update state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let stopSync: (() => void) | undefined;
    let cancelled = false;
    // eslint-disable-next-line no-void -- effect callbacks cannot be async
    void getAppDatabase().then(db => {
      if (!cancelled) stopSync = startAutoSync(db, { apiBaseUrl });
    });
    return () => {
      cancelled = true;
      stopSync?.();
    };
  }, [apiBaseUrl]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.page}>
        <View style={styles.tabBar}>
          <TabButton
            label="Create"
            active={tab === 'create'}
            onPress={() => setTab('create')}
            testID="tab-create"
          />
          <TabButton
            label="My reports"
            active={tab === 'reports'}
            onPress={() => setTab('reports')}
            testID="tab-reports"
          />
          <TabButton
            label="Nearby"
            active={tab === 'mesh'}
            onPress={() => setTab('mesh')}
            testID="tab-mesh"
          />
        </View>
        <View
          style={[
            styles.connectionBanner,
            nearby.active
              ? connectedCount(nearby) > 0
                ? styles.connectionBannerConnected
                : styles.connectionBannerSearching
              : styles.connectionBannerOff,
          ]}
          testID="global-connection-status"
        >
          <Text style={styles.connectionBannerText}>
            {nearby.active
              ? `Nearby active • ${connectedCount(nearby)} connected`
              : 'Nearby is off'}
          </Text>
        </View>
        {tab === 'create' && <ReportFormScreen onReportQueued={relayNewReport} />}
        {tab === 'reports' && <MyReportsScreen refreshToken={reportsRevision} />}
        {tab === 'mesh' && (
          <MeshScreen
            apiBaseUrl={apiBaseUrl}
            nearby={nearby}
            onApiBaseUrlChange={setApiBaseUrl}
          />
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

function connectedCount(nearby: NearbySession): number {
  return Object.keys(nearby.connectedPeers).length;
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#071a2c' },
  tabBar: { flexDirection: 'row', gap: 8, padding: 12 },
  tabButton: {
    flex: 1,
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#12283f',
  },
  tabButtonActive: { backgroundColor: '#c2410c' },
  tabLabel: { color: '#93a5b8', fontWeight: '600' },
  tabLabelActive: { color: '#ffffff', fontWeight: '700' },
  connectionBanner: {
    marginHorizontal: 12,
    marginBottom: 4,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  connectionBannerOff: { backgroundColor: '#334155' },
  connectionBannerSearching: { backgroundColor: '#92400e' },
  connectionBannerConnected: { backgroundColor: '#047857' },
  connectionBannerText: { color: '#ffffff', fontWeight: '700', textAlign: 'center' },
  meshPage: { flexGrow: 1, justifyContent: 'center', padding: 24 },
  card: { backgroundColor: '#ffffff', borderRadius: 16, padding: 24, gap: 14 },
  title: { fontSize: 32, fontWeight: '700', color: '#071a2c' },
  subtitle: { fontSize: 17, fontWeight: '600', color: '#c2410c' },
  detail: { fontSize: 15, color: '#374151', lineHeight: 22 },
  button: {
    backgroundColor: '#0f766e',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  buttonText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  buttonDisabled: { opacity: 0.6 },
  secondaryButton: {
    backgroundColor: '#334155',
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
  },
  backendInput: {
    borderColor: '#94a3b8',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#071a2c',
  },
  status: { color: '#374151' },
  heading: { fontSize: 16, fontWeight: '700', marginTop: 8 },
  endpoint: { color: '#0f766e' },
  connectedPeer: { color: '#047857', fontWeight: '700' },
  requestSection: { gap: 10, marginTop: 4 },
  requestRow: {
    backgroundColor: '#fff7ed',
    borderRadius: 10,
    padding: 12,
    gap: 8,
  },
  requestName: { color: '#7c2d12', fontWeight: '600' },
  authDigits: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 1,
  },
  requestActions: { flexDirection: 'row', gap: 8 },
  requestButton: {
    flex: 1,
    borderRadius: 8,
    paddingVertical: 8,
    alignItems: 'center',
  },
  acceptButton: { backgroundColor: '#0f766e' },
  declineButton: { backgroundColor: '#991b1b' },
  requestButtonText: { color: '#ffffff', fontWeight: '700' },
});

export default App;
