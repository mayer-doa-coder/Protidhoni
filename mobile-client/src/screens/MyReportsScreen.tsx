import {useCallback, useEffect, useState} from 'react';
import {FlatList, RefreshControl, StyleSheet, Text, View} from 'react-native';

import type {CrisisReport} from '../contracts/report';
import {getAppDatabase} from '../db/appDatabase';
import {listAllReports} from '../db/queue';

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

/** Roadmap §5.3: "a local 'my reports' view showing sync status (local /
 * relayed / synced) so a user isn't left wondering if their SOS actually
 * went anywhere." */
export function MyReportsScreen() {
  const [reports, setReports] = useState<CrisisReport[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const reload = useCallback(async () => {
    const db = await getAppDatabase();
    setReports(await listAllReports(db));
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
      data={reports}
      keyExtractor={item => item.message_id}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      ListEmptyComponent={<Text style={styles.empty}>No reports saved on this device yet.</Text>}
      renderItem={({item}) => (
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardType}>{item.type}</Text>
            <View style={[styles.statusPill, {backgroundColor: STATUS_COLOR[item.sync_status]}]}>
              <Text style={styles.statusPillText}>{item.sync_status}</Text>
            </View>
          </View>
          <Text style={styles.cardText} numberOfLines={3}>
            {item.payload.text}
          </Text>
          <Text style={styles.cardMeta}>{STATUS_LABEL[item.sync_status]}</Text>
          <Text style={styles.cardMeta}>{new Date(item.created_at).toLocaleString()}</Text>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c'},
  content: {padding: 16, gap: 10},
  empty: {color: '#93a5b8', textAlign: 'center', marginTop: 40},
  card: {backgroundColor: '#ffffff', borderRadius: 12, padding: 14, gap: 6},
  cardHeader: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'},
  cardType: {fontWeight: '700', color: '#071a2c'},
  statusPill: {borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3},
  statusPillText: {color: '#ffffff', fontSize: 11, fontWeight: '700'},
  cardText: {color: '#111827'},
  cardMeta: {color: '#6b7280', fontSize: 12},
});
