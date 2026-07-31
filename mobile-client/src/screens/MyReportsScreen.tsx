import {useCallback, useEffect, useState} from 'react';
import {FlatList, RefreshControl, StyleSheet, View} from 'react-native';

import type {CrisisReport} from '../contracts/report';
import {getAppDatabase} from '../db/appDatabase';
import {listReportRecords, type QueuedReportRecord} from '../db/queue';
import {getReportTypeLabel} from '../forms/reportFormConfig';
import {useLanguage} from '../i18n/LanguageContext';
import {translate, type AppLanguage} from '../i18n/translations';
import {AppText} from '../ui/AppText';
import {colors, radius, shadow, spacing} from '../ui/theme';

const STATUS_COLOR: Record<CrisisReport['sync_status'], string> = {
  local: colors.warning,
  relayed: colors.info,
  synced: colors.success,
};

type DeliveryPresentation = {message: string; color: string};

export function getDeliveryPresentation(
  record: QueuedReportRecord,
  language: AppLanguage = 'en',
): DeliveryPresentation {
  if (record.deliveryOutcome === 'accepted') {
    return {message: translate(language, 'reports.delivery.accepted'), color: '#15803d'};
  }
  if (record.deliveryOutcome === 'duplicate') {
    return {message: translate(language, 'reports.delivery.duplicate'), color: '#15803d'};
  }
  if (record.deliveryOutcome === 'rejected') {
    return {message: translate(language, 'reports.delivery.rejected'), color: '#b91c1c'};
  }
  if (record.deliveryFeedback) {
    return {message: translate(language, 'reports.delivery.retry'), color: '#b45309'};
  }
  return {
    message: translate(language, `reports.delivery.${record.report.sync_status}`),
    color: '#475569',
  };
}

/** Roadmap §5.3: "a local 'my reports' view showing sync status (local /
 * relayed / synced) so a user isn't left wondering if their SOS actually
 * went anywhere." */
export function MyReportsScreen({refreshToken = 0}: {refreshToken?: number} = {}) {
  const {formatDate, language, t} = useLanguage();
  const [records, setRecords] = useState<QueuedReportRecord[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const db = await getAppDatabase();
      setRecords(await listReportRecords(db));
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('reports.loadFailed.unknown'));
    }
  }, [t]);

  useEffect(() => {
    // eslint-disable-next-line no-void -- effect callbacks can't be async
    void reload();
  }, [refreshToken, reload]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    // eslint-disable-next-line no-void -- RefreshControl's onRefresh isn't awaited
    void reload().finally(() => setRefreshing(false));
  }, [reload]);

  return (
    <FlatList
      style={styles.page}
      contentContainerStyle={styles.content}
      data={records}
      keyExtractor={item => item.report.message_id}
      initialNumToRender={8}
      maxToRenderPerBatch={8}
      windowSize={5}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      ListHeaderComponent={
        loadError ? (
          <AppText style={styles.error}>
            {t('reports.loadFailed')} {loadError}
          </AppText>
        ) : null
      }
      ListEmptyComponent={
        loadError ? null : (
          <AppText style={styles.empty}>{t('reports.empty')}</AppText>
        )
      }
      renderItem={({item: record}) => {
        const item = record.report;
        const delivery = getDeliveryPresentation(record, language);
        return (
          <View style={styles.card} testID={`report-card-${item.message_id}`}>
            <View style={styles.cardHeader}>
              <AppText style={styles.cardType}>
                {getReportTypeLabel(item.type, language)}
              </AppText>
              <View style={[styles.statusPill, {backgroundColor: STATUS_COLOR[item.sync_status]}]}>
                <AppText style={styles.statusPillText}>
                  {t(`reports.status.${item.sync_status}`)}
                </AppText>
              </View>
            </View>
            <AppText style={styles.cardTimestamp} testID={`report-created-${item.message_id}`}>
              {t('reports.created', {date: formatDate(item.created_at)})}
            </AppText>
            <AppText style={styles.cardText} numberOfLines={3}>
              {item.payload.text}
            </AppText>
            <AppText
              style={[styles.deliveryFeedback, {color: delivery.color}]}
              testID={`report-delivery-${item.message_id}`}>
              {delivery.message}
            </AppText>
            {record.lastSyncAttemptAt && (
              <AppText style={styles.cardMeta}>
                {t('reports.lastAttempt', {
                  date: formatDate(record.lastSyncAttemptAt),
                })}
              </AppText>
            )}
          </View>
        );
      }}
    />
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: colors.background},
  content: {padding: spacing.lg, gap: spacing.sm},
  empty: {color: colors.inkMuted, textAlign: 'center', marginTop: 40},
  error: {color: colors.danger, backgroundColor: '#fee2e2', borderRadius: radius.sm, padding: 12},
  card: {backgroundColor: colors.surface, borderRadius: radius.md, padding: 14, gap: 6, ...shadow.card},
  cardHeader: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'},
  cardType: {fontWeight: '700', color: colors.ink},
  cardTimestamp: {color: colors.inkMuted, fontSize: 12},
  statusPill: {borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3},
  statusPillText: {color: colors.surface, fontSize: 11, fontWeight: '700'},
  cardText: {color: colors.ink},
  deliveryFeedback: {fontSize: 13, fontWeight: '600'},
  cardMeta: {color: colors.inkMuted, fontSize: 12},
});
