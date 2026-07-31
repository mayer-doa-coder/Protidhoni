import Geolocation from '@react-native-community/geolocation';
import {useMemo, useRef, useState} from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';

import {createSignedReport} from '../crypto/sign';
import type {CrisisReport} from '../contracts/report';
import {getAppDatabase} from '../db/appDatabase';
import {enqueueReport} from '../db/queue';
import {
  getReportFormConfig,
  getReportFormConfigs,
  type CreatableReportType,
} from '../forms/reportFormConfig';
import {buildReportDraft, type FormLocationInput} from '../forms/reportFormModel';
import {useLanguage} from '../i18n/LanguageContext';
import {AppText, AppTextInput} from '../ui/AppText';
import {colors, radius, shadow, spacing} from '../ui/theme';
import {fontFamilyForLanguage} from '../ui/typography';

async function requestLocationPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return true;
  const granted = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  return granted === PermissionsAndroid.RESULTS.GRANTED;
}

export function ReportFormScreen({
  initialType,
  onReportQueued,
}: {
  initialType?: CreatableReportType;
  onReportQueued?: (report: CrisisReport) => Promise<number>;
} = {}) {
  const {formatNumber, language, setLanguage, t} = useLanguage();
  const [reportType, setReportType] = useState<CreatableReportType>(initialType ?? 'SOS');
  const [text, setText] = useState('');
  const [peopleCount, setPeopleCount] = useState('');
  const [needs, setNeeds] = useState<ReadonlySet<string>>(new Set());
  const [location, setLocation] = useState<FormLocationInput>({source: 'none'});
  const [manualLat, setManualLat] = useState('');
  const [manualLng, setManualLng] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submissionInFlight = useRef(false);
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);
  const formConfigs = useMemo(() => getReportFormConfigs(language), [language]);
  const config = useMemo(
    () => getReportFormConfig(reportType, language),
    [language, reportType],
  );

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
        Alert.alert(
          t('report.permission.title'),
          t('report.permission.locationDenied'),
        );
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
        error => Alert.alert(t('report.locationUnavailable.title'), error.message),
        {enableHighAccuracy: true, timeout: 15000},
      );
    } catch (error) {
      Alert.alert(
        t('report.locationPermissionUnavailable.title'),
        error instanceof Error
          ? error.message
          : t('report.locationPermissionUnavailable.message'),
      );
    }
  };

  const submit = async () => {
    if (submissionInFlight.current) return;
    const locationInput: FormLocationInput =
      location.source === 'manual'
        ? {source: 'manual', lat: manualLat, lng: manualLng}
        : location;
    const result = buildReportDraft(
      {
        type: reportType,
        language,
        text,
        peopleCount,
        needs: [...needs],
        location: locationInput,
      },
      language,
    );
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
        throw new Error(t('report.duplicate'));
      }

      const relayedPeerCount = await onReportQueued?.(report) ?? 0;
      setLastSavedId(
        relayedPeerCount > 0
          ? t(
              relayedPeerCount === 1
                ? 'report.relayedDetails'
                : 'report.relayedDetailsPlural',
              {
                id: report.message_id,
                count: formatNumber(relayedPeerCount),
              },
            )
          : t('report.waitingDetails', {id: report.message_id}),
      );
      setText('');
      setPeopleCount('');
      setNeeds(new Set());
      setLocation({source: 'none'});
      setManualLat('');
      setManualLng('');
      Alert.alert(
        relayedPeerCount > 0
          ? t('report.alert.relayedTitle')
          : t('report.alert.offlineTitle'),
        relayedPeerCount > 0
          ? t(
              relayedPeerCount === 1
                ? 'report.alert.relayed'
                : 'report.alert.relayedPlural',
              {
                type: config.label,
                count: formatNumber(relayedPeerCount),
              },
            )
          : t('report.alert.offline', {type: config.label}),
      );
    } catch (error) {
      Alert.alert(
        t('report.saveFailed.title'),
        error instanceof Error ? error.message : t('report.unknownError'),
      );
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
      <AppText style={styles.title}>{t('report.title')}</AppText>
      <AppText style={styles.offlineHelper}>{t('report.offlineHelp')}</AppText>

      <AppText style={styles.label}>{t('report.type')}</AppText>
      <View style={styles.choiceRow}>
        {formConfigs.map(item => (
          <Pressable
            key={item.type}
            accessibilityRole="button"
            accessibilityState={{selected: reportType === item.type}}
            onPress={() => selectReportType(item.type)}
            style={[styles.choiceChip, reportType === item.type && styles.choiceChipSelected]}
            testID={`report-type-${item.type}`}>
            <AppText style={reportType === item.type ? styles.choiceTextSelected : styles.choiceText}>
              {item.shortLabel}
            </AppText>
          </Pressable>
        ))}
      </View>

      <View style={styles.formHeading}>
        <AppText style={styles.formTitle}>{config.label}</AppText>
        <AppText style={styles.formHelper}>{config.helper}</AppText>
      </View>

      <AppText style={styles.label}>{t('language.label')}</AppText>
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
            <AppText
              style={[
                language === value
                  ? styles.choiceTextSelected
                  : styles.choiceText,
                {fontFamily: fontFamilyForLanguage(value)},
              ]}>
              {label}
            </AppText>
          </Pressable>
        ))}
      </View>

      <AppText style={styles.label}>{config.descriptionLabel}</AppText>
      <AppTextInput
        style={styles.textArea}
        multiline
        placeholder={config.descriptionPlaceholder}
        value={text}
        onChangeText={setText}
        maxLength={2000}
        testID="report-description-input"
      />

      <AppText style={styles.label}>{config.peopleCountLabel}</AppText>
      <AppTextInput
        style={styles.input}
        keyboardType="number-pad"
        value={peopleCount}
        onChangeText={setPeopleCount}
        placeholder={t('report.people.placeholder')}
        maxLength={6}
        testID="report-people-count-input"
      />

      <AppText style={styles.label}>{config.needsLabel}</AppText>
      <View style={styles.choiceRow}>
        {config.needs.map(need => (
          <Pressable
            key={need.value}
            accessibilityRole="button"
            accessibilityState={{selected: needs.has(need.value)}}
            onPress={() => toggleNeed(need.value)}
            style={[styles.choiceChip, needs.has(need.value) && styles.needChipSelected]}
            testID={`report-need-${need.value}`}>
            <AppText style={needs.has(need.value) ? styles.choiceTextSelected : styles.choiceText}>
              {need.label}
            </AppText>
          </Pressable>
        ))}
      </View>

      <AppText style={styles.label}>{t('report.location')}</AppText>
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
          <AppText style={styles.locationButtonText}>{t('report.location.gps')}</AppText>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{selected: location.source === 'manual'}}
          style={[styles.locationButton, location.source === 'manual' && styles.locationButtonSelected]}
          onPress={() => setLocation({source: 'manual', lat: manualLat, lng: manualLng})}
          testID="report-location-manual">
          <AppText style={styles.locationButtonText}>{t('report.location.manual')}</AppText>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{selected: location.source === 'none'}}
          style={[styles.locationButton, location.source === 'none' && styles.locationButtonSelected]}
          onPress={() => setLocation({source: 'none'})}
          testID="report-location-none">
          <AppText style={styles.locationButtonText}>{t('report.location.none')}</AppText>
        </Pressable>
      </View>
      {location.source === 'gps' && (
        <AppText style={styles.locationSummary}>
          {t('report.location.gpsSummary', {
            lat: formatNumber(location.lat),
            lng: formatNumber(location.lng),
            accuracy: formatNumber(location.accuracyM),
          })}
        </AppText>
      )}
      {location.source === 'manual' && (
        <View style={styles.manualLocationRow}>
          <AppTextInput
            style={styles.manualInput}
            placeholder={t('report.location.latitude')}
            keyboardType="numbers-and-punctuation"
            value={manualLat}
            onChangeText={setManualLat}
            maxLength={16}
            testID="report-manual-lat-input"
          />
          <AppTextInput
            style={styles.manualInput}
            placeholder={t('report.location.longitude')}
            keyboardType="numbers-and-punctuation"
            value={manualLng}
            onChangeText={setManualLng}
            maxLength={16}
            testID="report-manual-lng-input"
          />
        </View>
      )}
      {location.source === 'none' && (
        <AppText style={styles.locationSummary}>
          {t('report.location.noneAttached')}
        </AppText>
      )}

      <Pressable
        accessibilityRole="button"
        style={[styles.submitButton, submitting && styles.submitButtonDisabled]}
        onPress={() => {
          // eslint-disable-next-line no-void -- Pressable handlers are synchronous
          void submit();
        }}
        disabled={submitting}
        testID="report-submit-button">
        <AppText style={styles.submitButtonText}>
          {submitting
            ? t('report.saving')
            : t('report.save', {type: config.shortLabel})}
        </AppText>
      </Pressable>
      {lastSavedId && (
        <AppText style={styles.confirmation}>
          {t('report.savedLocally', {details: lastSavedId})}
        </AppText>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: colors.background},
  content: {padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xxl},
  title: {fontSize: 22, fontWeight: '700', color: colors.ink},
  offlineHelper: {fontSize: 13, color: colors.inkMuted, marginBottom: 6},
  label: {fontSize: 14, fontWeight: '700', color: colors.ink, marginTop: 10},
  choiceRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  choiceChip: {
    borderRadius: radius.pill,
    paddingVertical: 7,
    paddingHorizontal: 12,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  choiceChipSelected: {backgroundColor: colors.primary, borderColor: colors.primary},
  needChipSelected: {backgroundColor: colors.info, borderColor: colors.info},
  choiceText: {color: colors.inkMuted},
  choiceTextSelected: {color: colors.surface, fontWeight: '700'},
  formHeading: {backgroundColor: colors.surface, borderRadius: radius.md, padding: 12, marginTop: 4, ...shadow.card},
  formTitle: {fontSize: 18, fontWeight: '700', color: colors.ink},
  formHelper: {fontSize: 13, color: colors.inkMuted, lineHeight: 19, marginTop: 3},
  textArea: {
    backgroundColor: colors.surface,
    color: colors.ink,
    borderRadius: radius.sm,
    padding: 12,
    minHeight: 96,
    textAlignVertical: 'top',
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  input: {
    backgroundColor: colors.surface,
    color: colors.ink,
    borderRadius: radius.sm,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  locationButton: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  locationButtonSelected: {borderColor: colors.primary, borderWidth: 1.5},
  locationButtonText: {color: colors.ink, fontWeight: '600'},
  locationSummary: {color: colors.inkMuted, fontSize: 13},
  manualLocationRow: {flexDirection: 'row', gap: 8},
  manualInput: {
    flex: 1,
    backgroundColor: colors.surface,
    color: colors.ink,
    borderRadius: radius.sm,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  submitButton: {marginTop: 16, backgroundColor: colors.primary, borderRadius: radius.sm, padding: 14, alignItems: 'center'},
  submitButtonDisabled: {opacity: 0.6},
  submitButtonText: {color: colors.surface, fontSize: 16, fontWeight: '700'},
  confirmation: {color: colors.success, fontSize: 12, marginTop: 8},
});
