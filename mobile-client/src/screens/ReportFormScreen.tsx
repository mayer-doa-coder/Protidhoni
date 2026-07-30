import Geolocation from '@react-native-community/geolocation';
import {useMemo, useRef, useState} from 'react';
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

import {createSignedReport} from '../crypto/sign';
import type {CrisisReport} from '../contracts/report';
import {getAppDatabase} from '../db/appDatabase';
import {enqueueReport} from '../db/queue';
import {
  getReportFormConfig,
  REPORT_FORM_CONFIGS,
  type CreatableReportType,
} from '../forms/reportFormConfig';
import {buildReportDraft, type FormLocationInput} from '../forms/reportFormModel';

async function requestLocationPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return true;
  const granted = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  return granted === PermissionsAndroid.RESULTS.GRANTED;
}

export function ReportFormScreen({
  onReportQueued,
}: {
  onReportQueued?: (report: CrisisReport) => Promise<number>;
} = {}) {
  const [reportType, setReportType] = useState<CreatableReportType>('SOS');
  const [language, setLanguage] = useState<'bn' | 'en'>('bn');
  const [text, setText] = useState('');
  const [peopleCount, setPeopleCount] = useState('');
  const [needs, setNeeds] = useState<ReadonlySet<string>>(new Set());
  const [location, setLocation] = useState<FormLocationInput>({source: 'none'});
  const [manualLat, setManualLat] = useState('');
  const [manualLng, setManualLng] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submissionInFlight = useRef(false);
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);
  const config = useMemo(() => getReportFormConfig(reportType), [reportType]);

  const selectReportType = (nextType: CreatableReportType) => {
    setReportType(nextType);
    setNeeds(new Set());
    setLastSavedId(null);
  };

  const toggleNeed = (need: string) => {
    setNeeds(current => {
      const next = new Set(current);
      if (next.has(need)) next.delete(need);
      else next.add(need);
      return next;
    });
  };

  const acquireGpsLocation = async () => {
    try {
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
            accuracyM: position.coords.accuracy,
          });
        },
        error => Alert.alert('Location unavailable', error.message),
        {enableHighAccuracy: true, timeout: 15000},
      );
    } catch (error) {
      Alert.alert(
        'Location permission unavailable',
        error instanceof Error ? error.message : 'Android could not complete the permission request.',
      );
    }
  };

  const submit = async () => {
    if (submissionInFlight.current) return;
    const locationInput: FormLocationInput =
      location.source === 'manual'
        ? {source: 'manual', lat: manualLat, lng: manualLng}
        : location;
    const result = buildReportDraft({
      type: reportType,
      language,
      text,
      peopleCount,
      needs: [...needs],
      location: locationInput,
    });
    if (!result.ok) {
      Alert.alert(result.error.title, result.error.message);
      return;
    }

    submissionInFlight.current = true;
    setSubmitting(true);
    try {
      const report = await createSignedReport(result.draft);
      const db = await getAppDatabase();
      const outcome = await enqueueReport(db, report);
      if (outcome !== 'inserted') {
        throw new Error('The generated report identifier already exists in the local queue.');
      }

      const relayedPeerCount = await onReportQueued?.(report) ?? 0;
      setLastSavedId(
        relayedPeerCount > 0
          ? `${report.message_id} • relayed to ${relayedPeerCount} peer${relayedPeerCount === 1 ? '' : 's'}`
          : `${report.message_id} • waiting for a peer`,
      );
      setText('');
      setPeopleCount('');
      setNeeds(new Set());
      setLocation({source: 'none'});
      setManualLat('');
      setManualLng('');
      Alert.alert(
        relayedPeerCount > 0 ? 'Report saved and relayed' : 'Report saved offline',
        relayedPeerCount > 0
          ? `${config.label} is safely stored on this phone and was relayed to ${relayedPeerCount} connected peer${relayedPeerCount === 1 ? '' : 's'}.`
          : `${config.label} is queued on this phone and will relay automatically when a peer connects.`,
      );
    } catch (error) {
      Alert.alert('Could not save report', error instanceof Error ? error.message : 'Unknown error.');
    } finally {
      submissionInFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>Create report</Text>
      <Text style={styles.offlineHelper}>
        Saved locally first. Internet is not required to create or queue a report.
      </Text>

      <Text style={styles.label}>Report type</Text>
      <View style={styles.choiceRow}>
        {REPORT_FORM_CONFIGS.map(item => (
          <Pressable
            key={item.type}
            accessibilityRole="button"
            accessibilityState={{selected: reportType === item.type}}
            onPress={() => selectReportType(item.type)}
            style={[styles.choiceChip, reportType === item.type && styles.choiceChipSelected]}
            testID={`report-type-${item.type}`}>
            <Text style={reportType === item.type ? styles.choiceTextSelected : styles.choiceText}>
              {item.shortLabel}
            </Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.formHeading}>
        <Text style={styles.formTitle}>{config.label}</Text>
        <Text style={styles.formHelper}>{config.helper}</Text>
      </View>

      <Text style={styles.label}>Language</Text>
      <View style={styles.choiceRow}>
        {([
          ['bn', 'বাংলা'],
          ['en', 'English'],
        ] as const).map(([value, label]) => (
          <Pressable
            key={value}
            accessibilityRole="button"
            accessibilityState={{selected: language === value}}
            onPress={() => setLanguage(value)}
            style={[styles.choiceChip, language === value && styles.choiceChipSelected]}
            testID={`report-language-${value}`}>
            <Text style={language === value ? styles.choiceTextSelected : styles.choiceText}>{label}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>{config.descriptionLabel}</Text>
      <TextInput
        style={styles.textArea}
        multiline
        placeholder={config.descriptionPlaceholder}
        value={text}
        onChangeText={setText}
        maxLength={2000}
        testID="report-description-input"
      />

      <Text style={styles.label}>{config.peopleCountLabel}</Text>
      <TextInput
        style={styles.input}
        keyboardType="number-pad"
        value={peopleCount}
        onChangeText={setPeopleCount}
        placeholder="e.g. 3"
        maxLength={6}
        testID="report-people-count-input"
      />

      <Text style={styles.label}>{config.needsLabel}</Text>
      <View style={styles.choiceRow}>
        {config.needs.map(need => (
          <Pressable
            key={need.value}
            accessibilityRole="button"
            accessibilityState={{selected: needs.has(need.value)}}
            onPress={() => toggleNeed(need.value)}
            style={[styles.choiceChip, needs.has(need.value) && styles.needChipSelected]}
            testID={`report-need-${need.value}`}>
            <Text style={needs.has(need.value) ? styles.choiceTextSelected : styles.choiceText}>
              {need.label}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Location</Text>
      <View style={styles.choiceRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{selected: location.source === 'gps'}}
          style={[styles.locationButton, location.source === 'gps' && styles.locationButtonSelected]}
          onPress={() => {
            // eslint-disable-next-line no-void -- Pressable handlers are synchronous
            void acquireGpsLocation();
          }}
          testID="report-location-gps">
          <Text style={styles.locationButtonText}>Use GPS</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{selected: location.source === 'manual'}}
          style={[styles.locationButton, location.source === 'manual' && styles.locationButtonSelected]}
          onPress={() => setLocation({source: 'manual', lat: manualLat, lng: manualLng})}
          testID="report-location-manual">
          <Text style={styles.locationButtonText}>Enter manually</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{selected: location.source === 'none'}}
          style={[styles.locationButton, location.source === 'none' && styles.locationButtonSelected]}
          onPress={() => setLocation({source: 'none'})}
          testID="report-location-none">
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
            maxLength={16}
            testID="report-manual-lat-input"
          />
          <TextInput
            style={styles.manualInput}
            placeholder="Longitude"
            keyboardType="numbers-and-punctuation"
            value={manualLng}
            onChangeText={setManualLng}
            maxLength={16}
            testID="report-manual-lng-input"
          />
        </View>
      )}
      {location.source === 'none' && <Text style={styles.locationSummary}>No location will be attached.</Text>}

      <Pressable
        accessibilityRole="button"
        style={[styles.submitButton, submitting && styles.submitButtonDisabled]}
        onPress={() => {
          // eslint-disable-next-line no-void -- Pressable handlers are synchronous
          void submit();
        }}
        disabled={submitting}
        testID="report-submit-button">
        <Text style={styles.submitButtonText}>{submitting ? 'Saving…' : `Save ${config.shortLabel}`}</Text>
      </Pressable>
      {lastSavedId && <Text style={styles.confirmation}>Saved locally: {lastSavedId}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c'},
  content: {padding: 16, gap: 8, paddingBottom: 32},
  title: {fontSize: 24, fontWeight: '700', color: '#ffffff'},
  offlineHelper: {fontSize: 13, color: '#93a5b8', marginBottom: 6},
  label: {fontSize: 14, fontWeight: '700', color: '#dbe4ee', marginTop: 10},
  choiceRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  choiceChip: {
    borderRadius: 16,
    paddingVertical: 7,
    paddingHorizontal: 12,
    backgroundColor: '#12283f',
    borderWidth: 1,
    borderColor: '#2a4a6b',
  },
  choiceChipSelected: {backgroundColor: '#c2410c', borderColor: '#c2410c'},
  needChipSelected: {backgroundColor: '#0f766e', borderColor: '#0f766e'},
  choiceText: {color: '#b8c7d9'},
  choiceTextSelected: {color: '#ffffff', fontWeight: '700'},
  formHeading: {backgroundColor: '#12283f', borderRadius: 10, padding: 12, marginTop: 4},
  formTitle: {fontSize: 18, fontWeight: '700', color: '#ffffff'},
  formHelper: {fontSize: 13, color: '#b8c7d9', lineHeight: 19, marginTop: 3},
  textArea: {
    backgroundColor: '#ffffff',
    color: '#111827',
    borderRadius: 10,
    padding: 12,
    minHeight: 96,
    textAlignVertical: 'top',
  },
  input: {backgroundColor: '#ffffff', color: '#111827', borderRadius: 10, padding: 12},
  locationButton: {backgroundColor: '#12283f', borderRadius: 10, paddingVertical: 8, paddingHorizontal: 12},
  locationButtonSelected: {borderColor: '#38bdf8', borderWidth: 1},
  locationButtonText: {color: '#dbe4ee', fontWeight: '600'},
  locationSummary: {color: '#93a5b8', fontSize: 13},
  manualLocationRow: {flexDirection: 'row', gap: 8},
  manualInput: {flex: 1, backgroundColor: '#ffffff', color: '#111827', borderRadius: 10, padding: 12},
  submitButton: {marginTop: 16, backgroundColor: '#c2410c', borderRadius: 10, padding: 14, alignItems: 'center'},
  submitButtonDisabled: {opacity: 0.6},
  submitButtonText: {color: '#ffffff', fontSize: 16, fontWeight: '700'},
  confirmation: {color: '#22c55e', fontSize: 12, marginTop: 8},
});
