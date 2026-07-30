import {useCallback, useEffect, useState} from 'react';
import {FlatList, RefreshControl, StyleSheet, Text, View} from 'react-native';

import type {CrisisReport} from '../contracts/report';
import {getAppDatabase} from '../db/appDatabase';
import {listReportRecords, type QueuedReportRecord} from '../db/queue';
import {REPORT_TYPE_LABELS} from '../forms/reportFormConfig';

const STATUS_LABEL: Record<CrisisReport['sync_status'], string> = {
  local: 'Saved on this phone only',
  relayed: 'Relayed over the mesh',
  synced: 'Synced to the server',
};

const STATUS_COLOR: Record<CrisisReport['sync_status'], string> = {
  local: '#f59e0b',
  relayed: '#38bdf8',
  synced: '#22c55e',
};

type DeliveryPresentation = {message: string; color: string};

export function getDeliveryPresentation(record: QueuedReportRecord): DeliveryPresentation {
  if (record.deliveryOutcome === 'accepted') {
    return {message: 'Delivered: accepted by the server', color: '#15803d'};
  }
  if (record.deliveryOutcome === 'duplicate') {
    return {message: 'Delivered: server confirmed an earlier copy', color: '#15803d'};
  }
  if (record.deliveryOutcome === 'rejected') {
    return {message: record.deliveryFeedback ?? 'Rejected by the server; queued for retry', color: '#b91c1c'};
  }
  if (record.deliveryFeedback) {
    return {message: record.deliveryFeedback, color: '#b45309'};
  }
  return {message: STATUS_LABEL[record.report.sync_status], color: '#475569'};
}

/** Roadmap §5.3: "a local 'my reports' view showing sync status (local /
 * relayed / synced) so a user isn't left wondering if their SOS actually
 * went anywhere." */
export function MyReportsScreen() {
  const [records, setRecords] = useState<QueuedReportRecord[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const db = await getAppDatabase();
      setRecords(await listReportRecords(db));
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'The local report database could not be read.');
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line no-void -- effect callbacks can't be async
    void reload();
  }, [reload]);

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
        loadError ? <Text style={styles.error}>Could not load reports: {loadError}</Text> : null
      }
      ListEmptyComponent={
        loadError ? null : <Text style={styles.empty}>No reports saved on this device yet.</Text>
      }
      renderItem={({item: record}) => {
        const item = record.report;
        const delivery = getDeliveryPresentation(record);
        return (
          <View style={styles.card} testID={`report-card-${item.message_id}`}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardType}>{REPORT_TYPE_LABELS[item.type]}</Text>
              <View style={[styles.statusPill, {backgroundColor: STATUS_COLOR[item.sync_status]}]}>
                <Text style={styles.statusPillText}>{item.sync_status}</Text>
              </View>
            </View>
            <Text style={styles.cardTimestamp} testID={`report-created-${item.message_id}`}>
              Created {new Date(item.created_at).toLocaleString()}
            </Text>
            <Text style={styles.cardText} numberOfLines={3}>
              {item.payload.text}
            </Text>
            <Text
              style={[styles.deliveryFeedback, {color: delivery.color}]}
              testID={`report-delivery-${item.message_id}`}>
              {delivery.message}
            </Text>
            {record.lastSyncAttemptAt && (
              <Text style={styles.cardMeta}>
                Last delivery attempt {new Date(record.lastSyncAttemptAt).toLocaleString()}
              </Text>
            )}
          </View>
        );
      }}
    />
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c'},
  content: {padding: 16, gap: 10},
  empty: {color: '#93a5b8', textAlign: 'center', marginTop: 40},
  error: {color: '#fecaca', backgroundColor: '#7f1d1d', borderRadius: 10, padding: 12},
  card: {backgroundColor: '#ffffff', borderRadius: 12, padding: 14, gap: 6},
  cardHeader: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'},
  cardType: {fontWeight: '700', color: '#071a2c'},
  cardTimestamp: {color: '#64748b', fontSize: 12},
  statusPill: {borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3},
  statusPillText: {color: '#ffffff', fontSize: 11, fontWeight: '700'},
  cardText: {color: '#111827'},
  deliveryFeedback: {fontSize: 13, fontWeight: '600'},
  cardMeta: {color: '#6b7280', fontSize: 12},
});
