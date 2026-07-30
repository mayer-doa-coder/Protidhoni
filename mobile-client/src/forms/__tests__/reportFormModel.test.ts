import AsyncStorage from '@react-native-async-storage/async-storage';

import type {CrisisReport} from '../../contracts/report';
import {_resetDeviceIdentityCacheForTests} from '../../crypto/identity';
import {createSignedReport} from '../../crypto/sign';
import {enqueueReport, initReportQueueSchema, listAllReports} from '../../db/queue';
import {createNodeSqliteExecutor} from '../../db/testSupport/nodeSqliteExecutor';
import {REPORT_FORM_CONFIGS} from '../reportFormConfig';
import {buildReportDraft, type ReportFormValues} from '../reportFormModel';

// identity.ts (imported transitively via ../../crypto/sign) wraps the device
// key via the native KeystoreWrap module; see src/native/__mocks__/KeystoreWrap.ts.
jest.mock('../../native/KeystoreWrap');

function validValues(overrides: Partial<ReportFormValues> = {}): ReportFormValues {
  return {
    type: 'SOS',
    language: 'bn',
    text: 'জরুরি সহায়তা প্রয়োজন',
    peopleCount: '2',
    needs: ['rescue'],
    location: {source: 'none'},
    ...overrides,
  };
}

describe('configuration-driven report forms', () => {
  beforeEach(async () => {
    _resetDeviceIdentityCacheForTests();
    await AsyncStorage.clear();
  });

  it('defines every user-creatable contract type exactly once', () => {
    expect(REPORT_FORM_CONFIGS.map(config => config.type)).toEqual([
      'SOS',
      'MEDICAL_NEED',
      'RESOURCE_NEED',
      'SHELTER_INFO',
      'HAZARD_UPDATE',
      'SAFETY_STATUS',
      'SAFE_ROUTE',
    ]);
    expect(new Set(REPORT_FORM_CONFIGS.map(config => config.type))).toHaveProperty('size', 7);
  });

  it.each(REPORT_FORM_CONFIGS)(
    'creates, signs, and queues $type entirely offline',
    async config => {
      const result = buildReportDraft(
        validValues({
          type: config.type,
          needs: config.needs.length > 0 ? [config.needs[0].value] : [],
        }),
      );
      expect(result.ok).toBe(true);
      if (!result.ok) throw new Error(result.error.message);

      const report = await createSignedReport(result.draft);
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await expect(enqueueReport(db, report)).resolves.toBe('inserted');

      const [stored] = await listAllReports(db);
      expect(stored.type).toBe(config.type);
      expect(stored.sync_status).toBe('local');
      expect(stored.payload.needs).toEqual(result.draft.payload.needs);
      expect(stored.signature.value).toHaveLength(86);
    },
  );

  it.each([
    ['empty description', {text: '   '}, 'Description required'],
    ['fractional people count', {peopleCount: '2.5'}, 'People count invalid'],
    ['zero people count', {peopleCount: '0'}, 'People count invalid'],
    ['excessive people count', {peopleCount: '100001'}, 'People count invalid'],
    ['unknown need', {needs: ['not-configured']}, 'Selection invalid'],
    ['duplicate need', {needs: ['rescue', 'rescue']}, 'Selection invalid'],
    [
      'out-of-range manual location',
      {location: {source: 'manual', lat: '91', lng: '90'}},
      'Location invalid',
    ],
    [
      'zero GPS accuracy',
      {location: {source: 'gps', lat: 23.81, lng: 90.41, accuracyM: 0}},
      'Location invalid',
    ],
  ] as const)('rejects %s before signing or queueing', (_caseName, override, title) => {
    const result = buildReportDraft(validValues(override as Partial<ReportFormValues>));
    expect(result).toEqual(expect.objectContaining({ok: false, error: expect.objectContaining({title})}));
  });

  it('normalizes text, people count, and manual coordinates into the signed draft', () => {
    const result = buildReportDraft(
      validValues({
        language: 'en',
        text: '  Route is open via the school road.  ',
        peopleCount: '12',
        needs: [],
        location: {source: 'manual', lat: '23.8103', lng: '90.4125'},
      }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.draft.payload.text).toBe('Route is open via the school road.');
    expect(result.draft.payload.people_count).toBe(12);
    expect(result.draft.location).toEqual({
      lat: 23.8103,
      lng: 90.4125,
      accuracy_m: null,
      source: 'manual',
    } satisfies CrisisReport['location']);
  });
});
