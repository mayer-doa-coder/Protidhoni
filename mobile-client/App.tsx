import {useEffect, useMemo, useState} from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  Pressable,
  type Permission,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';

import {getAppDatabase} from './src/db/appDatabase';
import {startMeshRelay} from './src/mesh/relay';
import {MyReportsScreen} from './src/screens/MyReportsScreen';
import {ReportFormScreen} from './src/screens/ReportFormScreen';
import {NearbyConnections} from './src/native/NearbyConnections';
import {startAutoSync} from './src/sync/sync';

/**
 * Where this device POSTs its queue when it regains connectivity
 * (src/sync/sync.ts). There is no settings UI yet — set it
 * for your demo network before building:
 *   - Android emulator: the default below (10.0.2.2 is the emulator's alias
 *     for the host machine's localhost).
 *   - A real phone on the same Wi-Fi as the machine running
 *     `docker compose up`: that machine's LAN IP, e.g. 'http://192.168.1.42:8000'.
 */
const API_BASE_URL = 'http://10.0.2.2:8000';

const endpointName = `Protidhoni-${Math.random().toString(36).slice(2, 8)}`;

async function requestNearbyPermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;

  const permissions: Permission[] = [];
  if (Platform.Version >= 31) {
    permissions.push(
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_ADVERTISE,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
    );
  } else if (Platform.Version >= 29) {
    permissions.push(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  }
  if (Platform.Version >= 32 && PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES) {
    permissions.push(PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES);
  }

  const results = await PermissionsAndroid.requestMultiple(permissions);
  return permissions.every(permission => results[permission] === PermissionsAndroid.RESULTS.GRANTED);
}

type Tab = 'create' | 'reports' | 'mesh';

function TabButton({label, active, onPress}: {label: string; active: boolean; onPress: () => void}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={[styles.tabButton, active && styles.tabButtonActive]}>
      <Text style={active ? styles.tabLabelActive : styles.tabLabel}>{label}</Text>
    </Pressable>
  );
}

function MeshScreen() {
  const [active, setActive] = useState(false);
  const [endpoints, setEndpoints] = useState<Record<string, string>>({});
  const endpointList = useMemo(() => Object.entries(endpoints), [endpoints]);

  useEffect(() => {
    const found = NearbyConnections.onEndpointFound(endpoint => {
      setEndpoints(current => ({...current, [endpoint.endpointId]: endpoint.name}));
    });
    const lost = NearbyConnections.onEndpointLost(endpoint => {
      setEndpoints(current => {
        const next = {...current};
        delete next[endpoint.endpointId];
        return next;
      });
    });
    return () => {
      found.remove();
      lost.remove();
      // eslint-disable-next-line no-void -- cleanup effect isn't awaited
      void NearbyConnections.stop();
    };
  }, []);

  const toggleNearby = async () => {
    if (active) {
      await NearbyConnections.stop();
      setEndpoints({});
      setActive(false);
      return;
    }
    if (!(await requestNearbyPermissions())) {
      Alert.alert('Permission needed', 'Nearby discovery cannot start until all requested nearby-device permissions are allowed.');
      return;
    }
    try {
      await NearbyConnections.start(endpointName);
      setActive(true);
    } catch (error) {
      Alert.alert('Nearby unavailable', error instanceof Error ? error.message : 'Unable to start discovery.');
    }
  };

  return (
    <View style={styles.meshPage}>
      <View style={styles.card}>
        <Text style={styles.title}>Protidhoni</Text>
        <Text style={styles.subtitle}>Offline peer mesh</Text>
        <Text style={styles.detail}>
          Advertises and discovers nearby devices, and auto-connects to exchange queued reports. Connection pairing
          confirmation (comparing digits between devices) is a Phase 3 hardening item, not built yet.
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
            void toggleNearby();
          }}
          style={styles.button}>
          <Text style={styles.buttonText}>{active ? 'Stop discovery' : 'Start nearby discovery'}</Text>
        </Pressable>
        <Text style={styles.status}>{active ? `Advertising as ${endpointName}` : 'Discovery stopped'}</Text>
        <Text style={styles.heading}>Devices in range ({endpointList.length})</Text>
        {endpointList.map(([id, name]) => (
          <Text key={id} style={styles.endpoint}>
            {name}
          </Text>
        ))}
      </View>
    </View>
  );
}

function App() {
  const [tab, setTab] = useState<Tab>('create');

  useEffect(() => {
    let stopRelay: (() => void) | undefined;
    let stopSync: (() => void) | undefined;
    let cancelled = false;

    // eslint-disable-next-line no-void -- effect callbacks can't be async
    void (async () => {
      const db = await getAppDatabase();
      if (cancelled) return;
      stopRelay = startMeshRelay(db);
      stopSync = startAutoSync(db, {apiBaseUrl: API_BASE_URL});
    })();

    return () => {
      cancelled = true;
      stopRelay?.();
      stopSync?.();
    };
  }, []);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.page}>
        <View style={styles.tabBar}>
          <TabButton label="Create" active={tab === 'create'} onPress={() => setTab('create')} />
          <TabButton label="My reports" active={tab === 'reports'} onPress={() => setTab('reports')} />
          <TabButton label="Nearby" active={tab === 'mesh'} onPress={() => setTab('mesh')} />
        </View>
        {tab === 'create' && <ReportFormScreen />}
        {tab === 'reports' && <MyReportsScreen />}
        {tab === 'mesh' && <MeshScreen />}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c'},
  tabBar: {flexDirection: 'row', gap: 8, padding: 12},
  tabButton: {flex: 1, borderRadius: 10, paddingVertical: 10, alignItems: 'center', backgroundColor: '#12283f'},
  tabButtonActive: {backgroundColor: '#c2410c'},
  tabLabel: {color: '#93a5b8', fontWeight: '600'},
  tabLabelActive: {color: '#ffffff', fontWeight: '700'},
  meshPage: {flex: 1, justifyContent: 'center', padding: 24},
  card: {backgroundColor: '#ffffff', borderRadius: 16, padding: 24, gap: 14},
  title: {fontSize: 32, fontWeight: '700', color: '#071a2c'},
  subtitle: {fontSize: 17, fontWeight: '600', color: '#c2410c'},
  detail: {fontSize: 15, color: '#374151', lineHeight: 22},
  button: {backgroundColor: '#0f766e', borderRadius: 10, padding: 14, alignItems: 'center'},
  buttonText: {color: '#ffffff', fontSize: 16, fontWeight: '700'},
  status: {color: '#374151'},
  heading: {fontSize: 16, fontWeight: '700', marginTop: 8},
  endpoint: {color: '#0f766e'},
});

export default App;
