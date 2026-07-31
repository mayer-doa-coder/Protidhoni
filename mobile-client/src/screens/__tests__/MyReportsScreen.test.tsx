import * as React from 'react';
import {create, act, type ReactTestRenderer} from 'react-test-renderer';

jest.mock('@op-engineering/op-sqlite', () => {
  const rows: unknown[] = [];
  const state: {error: Error | null} = {error: null};
  return {
    __mockRows: rows,
    __mockState: state,
    open: jest.fn(() => ({
      execute: jest.fn(async (sql: string) => {
        if (state.error) throw state.error;
        if (sql.trim().toUpperCase().startsWith('SELECT')) {
          return {rows, rowsAffected: 0};
        }
        return {rows: [], rowsAffected: 0};
      }),
    })),
  };
});

import {MyReportsScreen} from '../MyReportsScreen';

const mockRows = (jest.requireMock('@op-engineering/op-sqlite') as {__mockRows: unknown[]}).__mockRows;
const mockState = (jest.requireMock('@op-engineering/op-sqlite') as {__mockState: {error: Error | null}})
  .__mockState;

afterEach(() => {
  mockRows.length = 0;
  mockState.error = null;
});

test('renders the empty my-reports view without crashing', async () => {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<MyReportsScreen />);
    await Promise.resolve();
  });
  await act(async () => renderer!.unmount());
});

test('shows a database read error instead of claiming the queue is empty', async () => {
  mockState.error = new Error('database unavailable');
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<MyReportsScreen />);
    await Promise.resolve();
  });
  try {
    const errorNodes = renderer!.root.findAll(node => {
      const children = node.props.children as unknown;
      return Array.isArray(children) && children.join('').includes('database unavailable');
    });
    expect(errorNodes.length).toBeGreaterThan(0);
    expect(
      renderer!.root.findAll(node => node.props.children === 'No reports saved on this device yet.'),
    ).toHaveLength(0);
  } finally {
    await act(async () => renderer!.unmount());
  }
});

test('shows report type, timestamp, sync state, and rejection feedback', async () => {
  mockRows.push({
    report_json: JSON.stringify({
      schema_version: '1.0.0',
      message_id: '11111111-1111-4111-8111-111111111111',
      type: 'MEDICAL_NEED',
      sender_pubkey: 'A'.repeat(43),
      sender_pubkey_hash: 'B'.repeat(43),
      created_at: '2026-07-30T04:00:00.000Z',
      language: 'en',
      location: {lat: null, lng: null, accuracy_m: null, source: 'none'},
      payload: {text: 'Two people need medicine.', people_count: 2, needs: ['medicine'], attachment_ref: null},
      priority: null,
      ttl_hops: 8,
      signature: {algorithm: 'Ed25519', value: 'C'.repeat(86)},
      relay_path: [],
      sync_status: 'local',
      verification: {status: 'unverified', corroboration_count: 0},
    }),
    sync_status: 'relayed',
    queued_at: '2026-07-30T04:00:01.000Z',
    delivery_outcome: 'rejected',
    delivery_feedback: 'The server rejected this report. It remains queued and will retry.',
    last_sync_attempt_at: '2026-07-30T04:01:00.000Z',
  });

  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<MyReportsScreen />);
    await Promise.resolve();
  });
  try {
    const text = renderer!.root
      .findAll(node => typeof node.props.children === 'string')
      .map(node => node.props.children)
      .join(' ');
    expect(text).toContain('Medical need');
    expect(text).toContain('relayed');
    expect(
      renderer!.root.findByProps({testID: 'report-created-11111111-1111-4111-8111-111111111111'})
        .props.children,
    ).toContain('Created ');
    expect(
      renderer!.root.findByProps({testID: 'report-delivery-11111111-1111-4111-8111-111111111111'})
        .props.children,
    ).toContain('Rejected by the server');
  } finally {
    await act(async () => renderer!.unmount());
  }
});

test('reloads an already-open report list when its refresh token changes', async () => {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<MyReportsScreen refreshToken={0} />);
    await Promise.resolve();
  });

  mockRows.push({
    report_json: JSON.stringify({
      schema_version: '1.0.0',
      message_id: '22222222-2222-4222-8222-222222222222',
      type: 'SOS',
      sender_pubkey: 'A'.repeat(43),
      sender_pubkey_hash: 'B'.repeat(43),
      created_at: '2026-07-30T04:00:00.000Z',
      language: 'en',
      location: {lat: null, lng: null, accuracy_m: null, source: 'none'},
      payload: {text: 'Incoming mesh report', people_count: null, needs: [], attachment_ref: null},
      priority: null,
      ttl_hops: 7,
      signature: {algorithm: 'Ed25519', value: 'C'.repeat(86)},
      relay_path: ['D'.repeat(43)],
      sync_status: 'relayed',
      verification: {status: 'unverified', corroboration_count: 0},
    }),
    sync_status: 'relayed',
    queued_at: '2026-07-30T04:00:01.000Z',
    delivery_outcome: null,
    delivery_feedback: null,
    last_sync_attempt_at: null,
  });

  try {
    await act(async () => {
      renderer!.update(<MyReportsScreen refreshToken={1} />);
      await Promise.resolve();
    });
    expect(
      renderer!.root.findByProps({
        testID: 'report-card-22222222-2222-4222-8222-222222222222',
      }),
    ).toBeDefined();
  } finally {
    await act(async () => renderer!.unmount());
  }
});
