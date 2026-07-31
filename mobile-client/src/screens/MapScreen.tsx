import {useCallback, useEffect, useMemo, useState} from 'react';
import {Alert, Modal, Pressable, StyleSheet, View} from 'react-native';
import {Camera, Map, Marker, VectorSource} from '@maplibre/maplibre-react-native';
import type {StyleSpecification} from '@maplibre/maplibre-gl-style-spec';

import type {MapMark, MarkCategory} from '../contracts/mark';
import {createSignedMark} from '../crypto/mark';
import {getAppDatabase} from '../db/appDatabase';
import {enqueueMark, listMarks} from '../db/marks';
import {ensureAssetCopiedToStorage} from '../offline/assetStorage';
import {useLanguage} from '../i18n/LanguageContext';
import {AppText, AppTextInput} from '../ui/AppText';

const MBTILES_ASSET_PATH = 'maps/bangladesh.mbtiles';
const MBTILES_FILE_NAME = 'bangladesh.mbtiles';
const SOURCE_ID = 'protidhoni-offline';

// Bangladesh's approximate geographic centre (matches the generated
// bangladesh.mbtiles's own `center` metadata field).
const BANGLADESH_CENTER: [number, number] = [90.3474, 22.6154];

const CATEGORY_COLOR: Record<MarkCategory, string> = {
  HAZARD: '#dc2626',
  SAFE_ROUTE: '#16a34a',
  SHELTER: '#2563eb',
  RESOURCE: '#ca8a04',
  OTHER: '#6b7280',
};

const CATEGORIES: MarkCategory[] = ['HAZARD', 'SAFE_ROUTE', 'SHELTER', 'RESOURCE', 'OTHER'];

function buildOfflineStyle(mbtilesPath: string): StyleSpecification {
  // Real layer/field names confirmed against this project's own generated
  // bangladesh.mbtiles metadata (planetiler's OpenMapTiles-schema profile),
  // not assumed. `mbtiles://<path>` as a whole-source local-file URL is
  // documented, long-standing Mapbox/MapLibre Native functionality, but has
  // not been visually verified on-device in this session -- see the
  // "unverified" note in mobile-client/README.md before trusting it renders
  // correctly.
  const bengaliFirstName = ['coalesce', ['get', 'name:bn'], ['get', 'name']] as const;
  return {
    version: 8,
    // Required by the OpenMapTiles/OSM data license (data/README.md-style
    // rule: never drop attribution for data you didn't create yourself).
    sources: {
      [SOURCE_ID]: {
        type: 'vector',
        url: `mbtiles://${mbtilesPath}`,
        attribution: '© OpenMapTiles © OpenStreetMap contributors',
      },
    },
    layers: [
      {id: 'background', type: 'background', paint: {'background-color': '#eef2f5'}},
      {
        id: 'landcover',
        type: 'fill',
        source: SOURCE_ID,
        'source-layer': 'landcover',
        paint: {'fill-color': '#e3ead9', 'fill-opacity': 0.6},
      },
      {
        id: 'water',
        type: 'fill',
        source: SOURCE_ID,
        'source-layer': 'water',
        paint: {'fill-color': '#a9cbe8'},
      },
      {
        id: 'waterway',
        type: 'line',
        source: SOURCE_ID,
        'source-layer': 'waterway',
        paint: {'line-color': '#a9cbe8', 'line-width': 1},
      },
      {
        id: 'boundary',
        type: 'line',
        source: SOURCE_ID,
        'source-layer': 'boundary',
        filter: ['<=', ['get', 'admin_level'], 4],
        paint: {'line-color': '#9ca3af', 'line-width': 1, 'line-dasharray': [2, 2]},
      },
      {
        id: 'transportation-case',
        type: 'line',
        source: SOURCE_ID,
        'source-layer': 'transportation',
        paint: {'line-color': '#cbd5e1', 'line-width': 2.5},
      },
      {
        id: 'transportation',
        type: 'line',
        source: SOURCE_ID,
        'source-layer': 'transportation',
        paint: {'line-color': '#f8fafc', 'line-width': 1.5, 'line-gap-width': 0.5},
      },
      {
        id: 'water-name',
        type: 'symbol',
        source: SOURCE_ID,
        'source-layer': 'water_name',
        layout: {'text-field': bengaliFirstName as unknown as string, 'text-size': 11},
        paint: {'text-color': '#3b82f6'},
      },
      {
        id: 'place',
        type: 'symbol',
        source: SOURCE_ID,
        'source-layer': 'place',
        layout: {
          'text-field': bengaliFirstName as unknown as string,
          'text-size': ['match', ['get', 'class'], 'city', 15, 'town', 13, 11],
          'text-font': ['Noto Sans Regular'],
        },
        paint: {'text-color': '#111827', 'text-halo-color': '#ffffff', 'text-halo-width': 1.2},
      },
    ],
  };
}

type PlacingState = {lng: number; lat: number} | null;

export function MapScreen({
  marksRevision = 0,
  onMarkCreated = async () => 0,
}: {
  marksRevision?: number;
  onMarkCreated?: (mark: MapMark) => Promise<number>;
} = {}) {
  const {t} = useLanguage();
  const [mbtilesPath, setMbtilesPath] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [marks, setMarks] = useState<MapMark[]>([]);
  const [placingAt, setPlacingAt] = useState<PlacingState>(null);
  const [category, setCategory] = useState<MarkCategory>('HAZARD');
  const [label, setLabel] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    ensureAssetCopiedToStorage(MBTILES_ASSET_PATH, MBTILES_FILE_NAME)
      .then(path => {
        if (!cancelled) setMbtilesPath(path);
      })
      .catch(error => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const reloadMarks = useCallback(async () => {
    const db = await getAppDatabase();
    setMarks(await listMarks(db));
  }, []);

  useEffect(() => {
    // eslint-disable-next-line no-void -- effect callbacks can't be async
    void reloadMarks();
  }, [marksRevision, reloadMarks]);

  const style = useMemo(() => (mbtilesPath ? buildOfflineStyle(mbtilesPath) : null), [mbtilesPath]);

  const closePlacingSheet = useCallback(() => {
    setPlacingAt(null);
    setLabel('');
    setCategory('HAZARD');
  }, []);

  const saveMark = useCallback(async () => {
    if (!placingAt || label.trim().length === 0) return;
    setSaving(true);
    try {
      const mark = await createSignedMark({
        lat: placingAt.lat,
        lng: placingAt.lng,
        category,
        label: label.trim(),
      });
      const db = await getAppDatabase();
      await enqueueMark(db, mark);
      await onMarkCreated(mark);
      await reloadMarks();
      closePlacingSheet();
    } catch (error) {
      Alert.alert(
        t('map.saveFailed.title'),
        error instanceof Error ? error.message : t('map.saveFailed.message'),
      );
    } finally {
      setSaving(false);
    }
  }, [category, closePlacingSheet, label, onMarkCreated, placingAt, reloadMarks, t]);

  if (loadError) {
    return (
      <View style={styles.centered}>
        <AppText style={styles.errorText}>{t('map.loadFailed', {details: loadError})}</AppText>
      </View>
    );
  }

  if (!style) {
    return (
      <View style={styles.centered}>
        <AppText style={styles.status}>{t('map.preparing')}</AppText>
      </View>
    );
  }

  return (
    <View style={styles.page}>
      <Map
        style={styles.map}
        mapStyle={style}
        attribution
        onLongPress={event => {
          const [lng, lat] = event.nativeEvent.lngLat;
          setPlacingAt({lng, lat});
        }}>
        <Camera initialViewState={{center: BANGLADESH_CENTER, zoom: 6}} />
        <VectorSource id={SOURCE_ID} url={`mbtiles://${mbtilesPath}`} />
        {marks.map(mark => (
          <Marker key={mark.mark_id} id={mark.mark_id} lngLat={[mark.lng, mark.lat]}>
            <View
              style={[styles.markerDot, {backgroundColor: CATEGORY_COLOR[mark.category]}]}
            />
          </Marker>
        ))}
      </Map>
      <AppText style={styles.hint}>{t('map.longPressHint')}</AppText>

      <Modal visible={placingAt !== null} transparent animationType="slide" onRequestClose={closePlacingSheet}>
        <View style={styles.sheetBackdrop}>
          <View style={styles.sheet}>
            <AppText style={styles.sheetTitle}>{t('map.newMark.title')}</AppText>
            <View style={styles.categoryRow}>
              {CATEGORIES.map(value => (
                <Pressable
                  key={value}
                  onPress={() => setCategory(value)}
                  style={[
                    styles.categoryChip,
                    {borderColor: CATEGORY_COLOR[value]},
                    category === value && {backgroundColor: CATEGORY_COLOR[value]},
                  ]}>
                  <AppText
                    style={[
                      styles.categoryChipText,
                      category === value && styles.categoryChipTextActive,
                    ]}>
                    {t(`map.category.${value}` as const)}
                  </AppText>
                </Pressable>
              ))}
            </View>
            <AppTextInput
              accessibilityLabel={t('map.newMark.labelPlaceholder')}
              onChangeText={setLabel}
              placeholder={t('map.newMark.labelPlaceholder')}
              style={styles.labelInput}
              value={label}
              multiline
            />
            <View style={styles.sheetActions}>
              <Pressable onPress={closePlacingSheet} style={styles.cancelButton}>
                <AppText style={styles.cancelButtonText}>{t('map.newMark.cancel')}</AppText>
              </Pressable>
              <Pressable
                disabled={saving || label.trim().length === 0}
                onPress={() => {
                  // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
                  void saveMark();
                }}
                style={[
                  styles.saveButton,
                  (saving || label.trim().length === 0) && styles.saveButtonDisabled,
                ]}>
                <AppText style={styles.saveButtonText}>
                  {saving ? t('map.newMark.saving') : t('map.newMark.save')}
                </AppText>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1},
  map: {flex: 1},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  status: {color: '#475569'},
  errorText: {color: '#b91c1c', textAlign: 'center'},
  hint: {
    position: 'absolute',
    bottom: 12,
    alignSelf: 'center',
    backgroundColor: '#071a2ccc',
    color: '#ffffff',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    overflow: 'hidden',
  },
  markerDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: '#ffffff',
  },
  sheetBackdrop: {flex: 1, backgroundColor: '#00000066', justifyContent: 'flex-end'},
  sheet: {backgroundColor: '#ffffff', borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 20, gap: 12},
  sheetTitle: {fontSize: 18, fontWeight: '700', color: '#071a2c'},
  categoryRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  categoryChip: {borderWidth: 2, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 6},
  categoryChipText: {color: '#111827', fontWeight: '600'},
  categoryChipTextActive: {color: '#ffffff'},
  labelInput: {
    borderColor: '#94a3b8',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minHeight: 60,
    color: '#071a2c',
    textAlignVertical: 'top',
  },
  sheetActions: {flexDirection: 'row', gap: 10},
  cancelButton: {flex: 1, borderRadius: 10, padding: 12, alignItems: 'center', backgroundColor: '#e2e8f0'},
  cancelButtonText: {color: '#334155', fontWeight: '700'},
  saveButton: {flex: 1, borderRadius: 10, padding: 12, alignItems: 'center', backgroundColor: '#0f766e'},
  saveButtonDisabled: {opacity: 0.5},
  saveButtonText: {color: '#ffffff', fontWeight: '700'},
});
