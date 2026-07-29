import {describe, expect, it} from 'vitest';

import type {CrisisReport} from './api';
import {clusterReports} from './incidentClustering';

function report(overrides: Partial<CrisisReport> = {}): CrisisReport {
  return {
    schema_version: '1.0.0',
    message_id: crypto.randomUUID(),
    type: 'HAZARD_UPDATE',
    sender_pubkey_hash: 'sender-one',
    created_at: '2026-07-30T00:00:00.000Z',
    language: 'en',
    location: {lat: 23.8103, lng: 90.4125, accuracy_m: 10, source: 'gps'},
    payload: {text: 'Flood water rising near the school road', people_count: null, needs: ['rescue'], attachment_ref: null},
    priority: 'high',
    ttl_hops: 8,
    relay_path: [],
    sync_status: 'synced',
    verification: {status: 'unverified', corroboration_count: 0},
    ...overrides,
  };
}

describe('incident clustering', () => {
  it('groups nearby similar reports and counts independent senders', () => {
    const clusters = clusterReports([
      report(),
      report({
        message_id: 'second',
        sender_pubkey_hash: 'sender-two',
        created_at: '2026-07-30T00:01:00.000Z',
        location: {lat: 23.811, lng: 90.413, accuracy_m: 9, source: 'gps'},
        payload: {text: 'Flood water is rising by school road', people_count: 3, needs: ['rescue'], attachment_ref: null},
        verification: {status: 'corroborated', corroboration_count: 2},
      }),
      report({message_id: 'duplicate-sender', sender_pubkey_hash: 'sender-one', created_at: '2026-07-30T00:02:00.000Z'}),
    ]);

    expect(clusters).toHaveLength(1);
    expect(clusters[0].reports).toHaveLength(3);
    expect(clusters[0].independentSenderCount).toBe(2);
    expect(clusters[0].reportedCorroborationCount).toBe(2);
  });

  it('does not collapse reports that differ by type, distance, text, or location availability', () => {
    const clusters = clusterReports([
      report(),
      report({message_id: 'other-type', type: 'MEDICAL_NEED'}),
      report({message_id: 'far-away', location: {lat: 23.9, lng: 90.5, accuracy_m: 4, source: 'gps'}}),
      report({message_id: 'unrelated-text', payload: {text: 'Fire at the market', people_count: null, needs: [], attachment_ref: null}}),
      report({message_id: 'no-location', location: {lat: null, lng: null, accuracy_m: null, source: 'none'}}),
    ]);

    expect(clusters).toHaveLength(5);
    expect(clusters.find(cluster => cluster.reports[0].message_id === 'no-location')?.center).toBeNull();
  });

  it('keeps a scored low-priority incident above an unscored member', () => {
    const [cluster] = clusterReports([
      report({priority: null}),
      report({message_id: 'low', priority: 'low'}),
    ]);

    expect(cluster.priority).toBe('low');
  });
});
