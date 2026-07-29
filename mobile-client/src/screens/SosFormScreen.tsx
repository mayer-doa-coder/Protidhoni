import Geolocation from '@react-native-community/geolocation';
import {useState} from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import type {CrisisReport} from '../contracts/report';
import {createSignedReport} from '../crypto/sign';
import {getAppDatabase} from '../db/appDatabase';
import {enqueueReport} from '../db/queue';

const NEEDS_OPTIONS = ['water', 'medical', 'shelter', 'food', 'rescue'] as const;

type LocationState =
  | {source: 'none'}
  | {source: 'gps'; lat: number; lng: number; accuracyM: number}
  | {source: 'manual'};

async function requestLocationPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return true;
  const granted = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  return granted === PermissionsAndroid.RESULTS.GRANTED;
}

export function SosFormScreen() {
  const [text, setText] = useState('');
  const [peopleCount, setPeopleCount] = useState('');
  const [needs, setNeeds] = useState<ReadonlySet<string>>(new Set());
  const [location, setLocation] = useState<LocationState>({source: 'none'});
  const [manualLat, setManualLat] = useState('');
  const [manualLng, setManualLng] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);

  const toggleNeed = (need: string) => {
    setNeeds(current => {
      const next = new Set(current);
      if (next.has(need)) {
        next.delete(need);
      } else {
        next.add(need);
      }
      return next;
    });
  };

  const useGpsLocation = async () => {
    if (!(await requestLocationPermission())) {
      Alert.alert('Permission needed', 'Location permission was not granted.');
      return;
    }
    Geolocation.getCurrentPosition(
      position => {
        setLocation({
          source: 'gps',
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracyM: position.coords.accuracy ?? 0,
        });
      },
      error => Alert.alert('Location unavailable', error.message),
      {enableHighAccuracy: true, timeout: 15000},
    );
  };

  const buildLocationField = (): CrisisReport['location'] | null => {
    if (location.source === 'none') {
      return {lat: null, lng: null, accuracy_m: null, source: 'none'};
    }
    if (location.source === 'gps') {
      return {lat: location.lat, lng: location.lng, accuracy_m: location.accuracyM, source: 'gps'};
    }
    const lat = Number.parseFloat(manualLat);
    const lng = Number.parseFloat(manualLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return {lat, lng, accuracy_m: null, source: 'manual'};
  };

  const submit = async () => {
    if (text.trim().length === 0) {
      Alert.alert('Description required', 'Describe the emergency before sending.');
      return;
    }
    const locationField = buildLocationField();
    if (locationField === null) {
      Alert.alert('Location incomplete', 'Enter a valid latitude and longitude, or choose "No location".');
      return;
    }

    setSubmitting(true);
    try {
      const peopleCountValue = peopleCount.trim().length > 0 ? Number.parseInt(peopleCount, 10) : null;
      const report = await createSignedReport({
        type: 'SOS',
        language: 'bn',
        location: locationField,
        payload: {
          text: text.trim(),
          people_count: Number.isFinite(peopleCountValue) ? peopleCountValue : null,
          needs: Array.from(needs),
          attachment_ref: null,
        },
      });

      const db = await getAppDatabase();
      await enqueueReport(db, report);

      setLastSavedId(report.message_id);
      setText('');
      setPeopleCount('');
      setNeeds(new Set());
      setLocation({source: 'none'});
      Alert.alert('Saved', 'Your SOS is queued locally. It will relay over the mesh and sync automatically once online.');
    } catch (error) {
      Alert.alert('Could not save report', error instanceof Error ? error.message : 'Unknown error.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.content}>
      <Text style={styles.title}>SOS report</Text>
      <Text style={styles.helper}>
        Works fully offline — this is saved to your device immediately and relayed/synced as connectivity allows.
      </Text>

      <Text style={styles.label}>What&apos;s happening?</Text>
      <TextInput
        style={styles.textArea}
        multiline
        placeholder="Describe the emergency"
        value={text}
        onChangeText={setText}
        maxLength={2000}
        testID="sos-text-input"
      />

      <Text style={styles.label}>People affected (optional)</Text>
      <TextInput
        style={styles.input}
        keyboardType="number-pad"
        value={peopleCount}
        onChangeText={setPeopleCount}
        placeholder="e.g. 3"
        testID="sos-people-count-input"
      />

      <Text style={styles.label}>Needs</Text>
      <View style={styles.needsRow}>
        {NEEDS_OPTIONS.map(need => (
          <Pressable
            key={need}
            accessibilityRole="button"
            onPress={() => toggleNeed(need)}
            style={[styles.needChip, needs.has(need) && styles.needChipSelected]}>
            <Text style={needs.has(need) ? styles.needChipTextSelected : styles.needChipText}>{need}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Location</Text>
      <View style={styles.locationRow}>
        <Pressable accessibilityRole="button" style={styles.locationButton} onPress={useGpsLocation}>
          <Text style={styles.locationButtonText}>Use GPS</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          style={styles.locationButton}
          onPress={() => setLocation({source: 'manual'})}>
          <Text style={styles.locationButtonText}>Enter manually</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          style={styles.locationButton}
          onPress={() => setLocation({source: 'none'})}>
          <Text style={styles.locationButtonText}>No location</Text>
        </Pressable>
      </View>
      {location.source === 'gps' && (
        <Text style={styles.locationSummary}>
          GPS: {location.lat.toFixed(5)}, {location.lng.toFixed(5)} (±{location.accuracyM.toFixed(0)}m)
        </Text>
      )}
      {location.source === 'manual' && (
        <View style={styles.manualLocationRow}>
          <TextInput
            style={styles.manualInput}
            placeholder="Latitude"
            keyboardType="numbers-and-punctuation"
            value={manualLat}
            onChangeText={setManualLat}
            testID="sos-manual-lat-input"
          />
          <TextInput
            style={styles.manualInput}
            placeholder="Longitude"
            keyboardType="numbers-and-punctuation"
            value={manualLng}
            onChangeText={setManualLng}
            testID="sos-manual-lng-input"
          />
        </View>
      )}
      {location.source === 'none' && <Text style={styles.locationSummary}>No location will be attached.</Text>}

      <Pressable
        accessibilityRole="button"
        style={styles.submitButton}
        onPress={() => {
          // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
          void submit();
        }}
        disabled={submitting}
        testID="sos-submit-button">
        <Text style={styles.submitButtonText}>{submitting ? 'Saving…' : 'Save SOS report'}</Text>
      </Pressable>
      {lastSavedId && <Text style={styles.confirmation}>Queued: {lastSavedId}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c'},
  content: {padding: 20, gap: 10},
  title: {fontSize: 24, fontWeight: '700', color: '#ffffff'},
  helper: {fontSize: 13, color: '#93a5b8', marginBottom: 6},
  label: {fontSize: 14, fontWeight: '700', color: '#dbe4ee', marginTop: 8},
  textArea: {
    backgroundColor: '#ffffff',
    borderRadius: 10,
    padding: 12,
    minHeight: 90,
    textAlignVertical: 'top',
  },
  input: {backgroundColor: '#ffffff', borderRadius: 10, padding: 12},
  needsRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  needChip: {
    borderRadius: 16,
    paddingVertical: 6,
    paddingHorizontal: 14,
    backgroundColor: '#12283f',
    borderWidth: 1,
    borderColor: '#2a4a6b',
  },
  needChipSelected: {backgroundColor: '#0f766e', borderColor: '#0f766e'},
  needChipText: {color: '#93a5b8'},
  needChipTextSelected: {color: '#ffffff', fontWeight: '700'},
  locationRow: {flexDirection: 'row', gap: 8, flexWrap: 'wrap'},
  locationButton: {
    backgroundColor: '#12283f',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  locationButtonText: {color: '#dbe4ee', fontWeight: '600'},
  locationSummary: {color: '#93a5b8', fontSize: 13},
  manualLocationRow: {flexDirection: 'row', gap: 8},
  manualInput: {flex: 1, backgroundColor: '#ffffff', borderRadius: 10, padding: 12},
  submitButton: {
    marginTop: 16,
    backgroundColor: '#c2410c',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  submitButtonText: {color: '#ffffff', fontSize: 16, fontWeight: '700'},
  confirmation: {color: '#22c55e', fontSize: 12, marginTop: 8},
});
