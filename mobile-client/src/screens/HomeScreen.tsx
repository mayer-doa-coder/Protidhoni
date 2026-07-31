import {useCallback, useEffect, useRef, useState} from 'react';
import {Animated, Pressable, ScrollView, StyleSheet, View} from 'react-native';

import type {CrisisReport} from '../contracts/report';
import {createSignedReport} from '../crypto/sign';
import {getAppDatabase} from '../db/appDatabase';
import {enqueueReport} from '../db/queue';
import {
  getReportFormConfig,
  type CreatableReportType,
} from '../forms/reportFormConfig';
import {buildReportDraft} from '../forms/reportFormModel';
import {useLanguage} from '../i18n/LanguageContext';
import type {NearbySession} from '../mesh/useNearbySession';
import {AppText} from '../ui/AppText';
import {categoryTint, colors, radius, shadow, spacing} from '../ui/theme';
import {SosCallingScreen} from './SosCallingScreen';

const HOLD_TO_SEND_MS = 1500;

type CategoryReportType = Exclude<CreatableReportType, 'SOS'>;

const CATEGORY_TYPES: CategoryReportType[] = [
  'MEDICAL_NEED',
  'HAZARD_UPDATE',
  'RESOURCE_NEED',
  'SHELTER_INFO',
  'SAFETY_STATUS',
  'SAFE_ROUTE',
];

export function HomeScreen({
  nearby,
  connectedCount,
  onReportQueued,
  onSelectReportType,
}: {
  nearby: NearbySession;
  connectedCount: number;
  onReportQueued: (report: CrisisReport) => Promise<number>;
  onSelectReportType: (type: CreatableReportType) => void;
}) {
  const {formatNumber, language, t} = useLanguage();
  const [holding, setHolding] = useState(false);
  const [sending, setSending] = useState(false);
  const [calling, setCalling] = useState(false);
  const holdProgress = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(1)).current;
  const holdTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {toValue: 1.08, duration: 900, useNativeDriver: true}),
        Animated.timing(pulse, {toValue: 1, duration: 900, useNativeDriver: true}),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  const sendSos = useCallback(async () => {
    setSending(true);
    try {
      const draftResult = buildReportDraft(
        {
          type: 'SOS',
          language,
          text: t('home.sos.defaultText'),
          peopleCount: '',
          needs: [],
          location: {source: 'none'},
        },
        language,
      );
      if (!draftResult.ok) return;
      const report = await createSignedReport(draftResult.draft);
      const db = await getAppDatabase();
      const outcome = await enqueueReport(db, report);
      if (outcome === 'inserted') await onReportQueued(report);
      setCalling(true);
    } finally {
      setSending(false);
    }
  }, [language, onReportQueued, t]);

  const cancelHold = useCallback(() => {
    if (holdTimer.current) {
      clearTimeout(holdTimer.current);
      holdTimer.current = null;
    }
    setHolding(false);
    Animated.timing(holdProgress, {toValue: 0, duration: 150, useNativeDriver: false}).start();
  }, [holdProgress]);

  const beginHold = useCallback(() => {
    if (sending || calling) return;
    setHolding(true);
    Animated.timing(holdProgress, {
      toValue: 1,
      duration: HOLD_TO_SEND_MS,
      useNativeDriver: false,
    }).start();
    holdTimer.current = setTimeout(() => {
      setHolding(false);
      // eslint-disable-next-line no-void -- timer callback cannot await
      void sendSos();
    }, HOLD_TO_SEND_MS);
  }, [calling, holdProgress, sendSos, sending]);

  if (calling) {
    return (
      <SosCallingScreen
        connectedPeerNames={Object.values(nearby.connectedPeers)}
        onDone={() => setCalling(false)}
      />
    );
  }

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.content}>
      <View style={styles.topBar}>
        <View style={styles.brandBadge}>
          <AppText style={styles.brandBadgeText}>প্র</AppText>
        </View>
        <View style={styles.topBarText}>
          <AppText style={styles.topBarTitle}>{t('mesh.title')}</AppText>
          <AppText style={styles.topBarSubtitle}>
            {connectedCount > 0
              ? t('connection.active', {count: formatNumber(connectedCount)})
              : t('connection.off')}
          </AppText>
        </View>
      </View>

      <View style={styles.emergencyCard}>
        <AppText style={styles.emergencyTitle}>{t('home.emergency.title')}</AppText>
        <AppText style={styles.emergencyBody}>{t('home.emergency.body')}</AppText>
      </View>

      <View style={styles.sosWrap}>
        <Animated.View style={[styles.sosRing, {transform: [{scale: pulse}]}]} />
        <Animated.View
          style={[
            styles.sosProgressRing,
            {
              opacity: holdProgress.interpolate({inputRange: [0, 1], outputRange: [0, 1]}),
              transform: [
                {
                  scale: holdProgress.interpolate({inputRange: [0, 1], outputRange: [0.94, 1.08]}),
                },
              ],
            },
          ]}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('home.sos.button')}
          onPressIn={beginHold}
          onPressOut={cancelHold}
          disabled={sending}
          style={styles.sosButton}
          testID="home-sos-button">
          <AppText style={styles.sosButtonText}>{t('home.sos.label')}</AppText>
          <AppText style={styles.sosButtonHint}>
            {holding || sending ? t('home.sos.holding') : t('home.sos.hint')}
          </AppText>
        </Pressable>
      </View>

      <AppText style={styles.sectionHeading}>{t('home.categories.heading')}</AppText>
      <View style={styles.categoryGrid}>
        {CATEGORY_TYPES.map(type => {
          const config = getReportFormConfig(type, language);
          return (
            <Pressable
              key={type}
              accessibilityRole="button"
              onPress={() => onSelectReportType(type)}
              style={styles.categoryChip}
              testID={`home-category-${type}`}>
              <View style={[styles.categoryBadge, {backgroundColor: categoryTint[type]}]}>
                <AppText style={styles.categoryBadgeText}>{config.shortLabel.slice(0, 1)}</AppText>
              </View>
              <AppText style={styles.categoryLabel}>{config.shortLabel}</AppText>
            </Pressable>
          );
        })}
      </View>
    </ScrollView>
  );
}

const SOS_BUTTON_SIZE = 176;

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: colors.background},
  content: {padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.lg},
  topBar: {flexDirection: 'row', alignItems: 'center', gap: spacing.md},
  brandBadge: {
    width: 42,
    height: 42,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.card,
  },
  brandBadgeText: {color: colors.primary, fontWeight: '800'},
  topBarText: {flex: 1},
  topBarTitle: {color: colors.ink, fontWeight: '700', fontSize: 16},
  topBarSubtitle: {color: colors.inkMuted, fontSize: 12, marginTop: 1},
  emergencyCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.xs,
    ...shadow.card,
  },
  emergencyTitle: {color: colors.ink, fontSize: 20, fontWeight: '700'},
  emergencyBody: {color: colors.inkMuted, fontSize: 14, lineHeight: 20},
  sosWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    height: SOS_BUTTON_SIZE + 64,
  },
  sosRing: {
    position: 'absolute',
    width: SOS_BUTTON_SIZE + 48,
    height: SOS_BUTTON_SIZE + 48,
    borderRadius: (SOS_BUTTON_SIZE + 48) / 2,
    backgroundColor: colors.surface,
  },
  sosProgressRing: {
    position: 'absolute',
    width: SOS_BUTTON_SIZE + 24,
    height: SOS_BUTTON_SIZE + 24,
    borderRadius: (SOS_BUTTON_SIZE + 24) / 2,
    borderWidth: 4,
    borderColor: colors.primaryDark,
  },
  sosButton: {
    width: SOS_BUTTON_SIZE,
    height: SOS_BUTTON_SIZE,
    borderRadius: SOS_BUTTON_SIZE / 2,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  sosButtonText: {color: colors.surface, fontSize: 32, fontWeight: '800'},
  sosButtonHint: {color: colors.surface, fontSize: 11, opacity: 0.9},
  sectionHeading: {color: colors.ink, fontSize: 16, fontWeight: '700'},
  categoryGrid: {flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm},
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
    borderRadius: radius.pill,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  categoryBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  categoryBadgeText: {color: colors.ink, fontWeight: '800', fontSize: 13},
  categoryLabel: {color: colors.ink, fontSize: 13, fontWeight: '600'},
});
