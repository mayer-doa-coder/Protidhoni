import {useEffect, useMemo, useState} from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  Pressable,
  type Permission,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {NearbyConnections} from './src/native/NearbyConnections';

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

function App() {
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
    <SafeAreaView style={styles.page}>
      <View style={styles.card}>
        <Text style={styles.title}>Protidhoni</Text>
        <Text style={styles.subtitle}>Phase 0: offline peer discovery</Text>
        <Text style={styles.detail}>This screen advertises and discovers nearby test devices. It does not send reports or auto-connect.</Text>
        <Pressable accessibilityRole="button" onPress={toggleNearby} style={styles.button}>
          <Text style={styles.buttonText}>{active ? 'Stop discovery' : 'Start nearby discovery'}</Text>
        </Pressable>
        <Text style={styles.status}>{active ? `Advertising as ${endpointName}` : 'Discovery stopped'}</Text>
        <Text style={styles.heading}>Devices in range ({endpointList.length})</Text>
        {endpointList.map(([id, name]) => <Text key={id} style={styles.endpoint}>{name}</Text>)}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c', justifyContent: 'center', padding: 24},
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
