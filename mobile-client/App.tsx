import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { MapMark } from './src/contracts/mark';
import type { CrisisReport } from './src/contracts/report';
import { getAppDatabase } from './src/db/appDatabase';
import type { CreatableReportType } from './src/forms/reportFormConfig';
import { startMeshRelay, type MeshRelayController } from './src/mesh/relay';
import {
  useNearbySession,
  type NearbySession,
} from './src/mesh/useNearbySession';
import { ChatScreen } from './src/screens/ChatScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { MapScreen } from './src/screens/MapScreen';
import { MyReportsScreen } from './src/screens/MyReportsScreen';
import { ReportFormScreen } from './src/screens/ReportFormScreen';
import { startAutoSync } from './src/sync/sync';
import {
  BackendOriginError,
  defaultBackendOrigin,
  loadBackendOrigin,
  saveBackendOrigin,
} from './src/config/backend';
import {
  LanguageProvider,
  useLanguage,
} from './src/i18n/LanguageContext';
import {AppText, AppTextInput} from './src/ui/AppText';
import {colors, radius, shadow, spacing} from './src/ui/theme';
import {fontFamilyForLanguage} from './src/ui/typography';

type Tab = 'home' | 'reports' | 'map' | 'chat' | 'mesh';

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
      <AppText style={active ? styles.tabLabelActive : styles.tabLabel}>
        {label}
      </AppText>
    </Pressable>
  );
}

function LanguageToggle() {
  const {language, setLanguage, t} = useLanguage();
  return (
    <View style={styles.languageBar}>
      <AppText style={styles.languageLabel}>{t('language.label')}</AppText>
      <View style={styles.languageChoices}>
        <Pressable
          accessibilityLabel={t('language.switchToBangla')}
          accessibilityRole="button"
          accessibilityState={{selected: language === 'bn'}}
          onPress={() => setLanguage('bn')}
          style={[
            styles.languageButton,
            language === 'bn' && styles.languageButtonActive,
          ]}
          testID="app-language-bn">
          <AppText
            style={[
              styles.languageButtonText,
              language === 'bn' && styles.languageButtonTextActive,
              {fontFamily: fontFamilyForLanguage('bn')},
            ]}>
            বাংলা
          </AppText>
        </Pressable>
        <Pressable
          accessibilityLabel={t('language.switchToEnglish')}
          accessibilityRole="button"
          accessibilityState={{selected: language === 'en'}}
          onPress={() => setLanguage('en')}
          style={[
            styles.languageButton,
            language === 'en' && styles.languageButtonActive,
          ]}
          testID="app-language-en">
          <AppText
            style={[
              styles.languageButtonText,
              language === 'en' && styles.languageButtonTextActive,
              {fontFamily: fontFamilyForLanguage('en')},
            ]}>
            English
          </AppText>
        </Pressable>
      </View>
    </View>
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
  const {formatNumber, t} = useLanguage();
  const [backendDraft, setBackendDraft] = useState(apiBaseUrl);
  const [backendFeedback, setBackendFeedback] = useState<
    {kind: 'saved'} | {kind: 'error'; message?: string} | null
  >(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
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
      setBackendFeedback({kind: 'saved'});
    } catch (error) {
      setBackendFeedback({
        kind: 'error',
        message:
          error instanceof BackendOriginError
            ? t(`mesh.backend.${error.reasonKey}`)
            : undefined,
      });
    }
  };

  const toggleNearby = async () => {
    if (nearby.active) await nearby.stop();
    else await nearby.start();
  };

  return (
    <ScrollView contentContainerStyle={styles.meshPage} keyboardShouldPersistTaps="handled">
      <View style={styles.card}>
        <AppText style={styles.title}>{t('mesh.title')}</AppText>
        <AppText style={styles.subtitle}>{t('mesh.subtitle')}</AppText>
        <AppText style={styles.detail}>{t('mesh.description')}</AppText>
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
            void toggleNearby();
          }}
          disabled={nearby.starting}
          style={[styles.button, nearby.starting && styles.buttonDisabled]}
        >
          <AppText style={styles.buttonText}>
            {nearby.starting
              ? t('mesh.starting')
              : nearby.active
                ? t('mesh.stop')
                : t('mesh.start')}
          </AppText>
        </Pressable>
        <AppText style={styles.status} testID="nearby-session-detail">
          {nearby.statusMessage}
        </AppText>
      </View>

      {pendingRequestList.length > 0 && (
        <View style={styles.card}>
          <View style={styles.requestSection}>
            <AppText style={styles.heading}>
              {t('mesh.requests', {
                count: formatNumber(pendingRequestList.length),
              })}
            </AppText>
            {pendingRequestList.map(([endpointId, request]) => (
              <View key={endpointId} style={styles.requestRow}>
                <AppText style={styles.requestName}>
                  {t('mesh.connectQuestion', {name: request.name})}
                </AppText>
                <AppText style={styles.authDigits}>
                  {t('mesh.confirmDigits', {
                    digits: request.authenticationDigits,
                  })}
                </AppText>
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
                    <AppText style={styles.requestButtonText}>
                      {t('mesh.accept')}
                    </AppText>
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
                    <AppText style={styles.requestButtonText}>
                      {t('mesh.decline')}
                    </AppText>
                  </Pressable>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      <View style={styles.card}>
        <AppText style={styles.heading} testID="connected-peer-count">
          {t('mesh.connectedPeers', {
            count: formatNumber(connectedPeerList.length),
          })}
        </AppText>
        {connectedPeerList.length === 0 ? (
          <AppText style={styles.status}>{t('mesh.noConnections')}</AppText>
        ) : (
          connectedPeerList.map(([id, name]) => (
            <AppText key={id} style={styles.connectedPeer}>
              ● {name}
            </AppText>
          ))
        )}
        <AppText style={styles.heading}>
          {t('mesh.devicesInRange', {
            count: formatNumber(endpointList.length),
          })}
        </AppText>
        {endpointList.length === 0 ? (
          <AppText style={styles.status}>{t('mesh.noneInRange')}</AppText>
        ) : (
          endpointList.map(([id, name]) => (
            <AppText key={id} style={styles.endpoint}>
              {name}
            </AppText>
          ))
        )}
      </View>

      <View style={styles.card}>
        <Pressable
          accessibilityRole="button"
          onPress={() => setShowAdvanced(current => !current)}
          style={styles.advancedToggle}
          testID="mesh-advanced-toggle"
        >
          <AppText style={styles.heading}>{t('mesh.backend.heading')}</AppText>
          <AppText style={styles.advancedToggleIcon}>{showAdvanced ? '−' : '+'}</AppText>
        </Pressable>
        {showAdvanced && (
          <>
            <AppText style={styles.detail}>{t('mesh.backend.help')}</AppText>
            <AppTextInput
              accessibilityLabel={t('mesh.backend.url')}
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
              <AppText style={styles.buttonText}>{t('mesh.backend.save')}</AppText>
            </Pressable>
            {backendFeedback ? (
              <AppText style={styles.status}>
                {backendFeedback.kind === 'saved'
                  ? t('mesh.backend.saved')
                  : backendFeedback.message ?? t('mesh.backend.saveFailed')}
              </AppText>
            ) : null}
          </>
        )}
      </View>
    </ScrollView>
  );
}

function AppContent() {
  const {formatNumber, t} = useLanguage();
  const [tab, setTab] = useState<Tab>('home');
  const [activeReportType, setActiveReportType] = useState<CreatableReportType | null>(null);
  const [apiBaseUrl, setApiBaseUrl] = useState(defaultBackendOrigin);
  const [reportsRevision, setReportsRevision] = useState(0);
  const [marksRevision, setMarksRevision] = useState(0);
  const nearby = useNearbySession();
  const relayRef = useRef<MeshRelayController | null>(null);
  const relayReadyRef = useRef<Promise<MeshRelayController | null> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const ready = getAppDatabase().then(db => {
      if (cancelled) return null;
      const relay = startMeshRelay(db, () => {
        setReportsRevision(current => current + 1);
        setMarksRevision(current => current + 1);
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

  const relayNewMark = useCallback(async (mark: MapMark): Promise<number> => {
    const relay = relayRef.current ?? (await relayReadyRef.current);
    return relay?.relayMark(mark) ?? 0;
  }, []);

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

  const selectTab = (next: Tab) => {
    setActiveReportType(null);
    setTab(next);
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.page}>
        {activeReportType === null && <LanguageToggle />}
        {activeReportType === null && (
          <>
            <View style={styles.tabBar}>
              <TabButton
                label={t('tab.home')}
                active={tab === 'home'}
                onPress={() => selectTab('home')}
                testID="tab-home"
              />
              <TabButton
                label={t('tab.reports')}
                active={tab === 'reports'}
                onPress={() => selectTab('reports')}
                testID="tab-reports"
              />
              <TabButton
                label={t('tab.map')}
                active={tab === 'map'}
                onPress={() => selectTab('map')}
                testID="tab-map"
              />
              <TabButton
                label={t('tab.chat')}
                active={tab === 'chat'}
                onPress={() => selectTab('chat')}
                testID="tab-chat"
              />
              <TabButton
                label={t('tab.nearby')}
                active={tab === 'mesh'}
                onPress={() => selectTab('mesh')}
                testID="tab-mesh"
              />
            </View>
            {tab !== 'home' && (
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
                <AppText style={styles.connectionBannerText}>
                  {nearby.active
                    ? t('connection.active', {
                        count: formatNumber(connectedCount(nearby)),
                      })
                    : t('connection.off')}
                </AppText>
              </View>
            )}
          </>
        )}
        {activeReportType !== null ? (
          <>
            <Pressable
              accessibilityRole="button"
              onPress={() => setActiveReportType(null)}
              style={styles.backButton}
              testID="report-detail-back"
            >
              <AppText style={styles.backButtonText}>{t('home.back')}</AppText>
            </Pressable>
            <ReportFormScreen initialType={activeReportType} onReportQueued={relayNewReport} />
          </>
        ) : (
          <>
            {tab === 'home' && (
              <HomeScreen
                nearby={nearby}
                connectedCount={connectedCount(nearby)}
                onReportQueued={relayNewReport}
                onSelectReportType={setActiveReportType}
              />
            )}
            {tab === 'reports' && <MyReportsScreen refreshToken={reportsRevision} />}
            {tab === 'map' && (
              <MapScreen marksRevision={marksRevision} onMarkCreated={relayNewMark} />
            )}
            {tab === 'chat' && <ChatScreen />}
            {tab === 'mesh' && (
              <MeshScreen
                apiBaseUrl={apiBaseUrl}
                nearby={nearby}
                onApiBaseUrlChange={setApiBaseUrl}
              />
            )}
          </>
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

function App() {
  return (
    <LanguageProvider>
      <AppContent />
    </LanguageProvider>
  );
}

function connectedCount(nearby: NearbySession): number {
  return Object.keys(nearby.connectedPeers).length;
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  languageBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 8,
    paddingHorizontal: 12,
    paddingTop: 10,
  },
  languageLabel: {color: colors.ink, fontWeight: '700'},
  languageChoices: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: 18,
    padding: 2,
    ...shadow.card,
  },
  languageButton: {borderRadius: 16, paddingHorizontal: 12, paddingVertical: 5},
  languageButtonActive: {backgroundColor: colors.primary},
  languageButtonText: {color: colors.inkMuted, fontWeight: '600'},
  languageButtonTextActive: {color: colors.surface, fontWeight: '800'},
  tabBar: { flexDirection: 'row', gap: 6, padding: 12 },
  tabButton: {
    flex: 1,
    borderRadius: radius.sm,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: colors.surface,
  },
  tabButtonActive: { backgroundColor: colors.primary },
  tabLabel: { color: colors.inkMuted, fontWeight: '600', fontSize: 12 },
  tabLabelActive: { color: colors.surface, fontWeight: '700', fontSize: 12 },
  connectionBanner: {
    marginHorizontal: 12,
    marginBottom: 4,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  connectionBannerOff: { backgroundColor: colors.neutral },
  connectionBannerSearching: { backgroundColor: colors.warning },
  connectionBannerConnected: { backgroundColor: colors.success },
  connectionBannerText: { color: colors.surface, fontWeight: '700', textAlign: 'center' },
  meshPage: { flexGrow: 1, padding: spacing.lg, gap: spacing.md, backgroundColor: colors.background },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: 10, ...shadow.card },
  title: { fontSize: 22, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 15, fontWeight: '600', color: colors.primaryDark },
  detail: { fontSize: 14, color: colors.inkMuted, lineHeight: 20 },
  button: {
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    padding: 14,
    alignItems: 'center',
  },
  buttonText: { color: colors.surface, fontSize: 16, fontWeight: '700' },
  buttonDisabled: { opacity: 0.6 },
  secondaryButton: {
    backgroundColor: colors.background,
    borderRadius: radius.sm,
    padding: 12,
    alignItems: 'center',
  },
  backendInput: {
    borderColor: colors.surfaceBorder,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.ink,
  },
  status: { color: colors.inkMuted },
  heading: { fontSize: 15, fontWeight: '700', color: colors.ink },
  endpoint: { color: colors.info },
  connectedPeer: { color: colors.success, fontWeight: '700' },
  requestSection: { gap: 10 },
  requestRow: {
    backgroundColor: '#FFF1E6',
    borderRadius: radius.sm,
    padding: 12,
    gap: 8,
  },
  requestName: { color: colors.primaryDark, fontWeight: '600' },
  authDigits: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 1,
  },
  requestActions: { flexDirection: 'row', gap: 8 },
  requestButton: {
    flex: 1,
    borderRadius: radius.sm,
    paddingVertical: 8,
    alignItems: 'center',
  },
  acceptButton: { backgroundColor: colors.success },
  declineButton: { backgroundColor: colors.danger },
  requestButtonText: { color: colors.surface, fontWeight: '700' },
  advancedToggle: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  advancedToggleIcon: { color: colors.primaryDark, fontWeight: '800', fontSize: 18 },
  backButton: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.xs },
  backButtonText: { color: colors.ink, fontWeight: '700' },
});

export default App;
