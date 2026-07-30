import {describe, expect, it} from 'vitest';

import type {CrisisReport, ReportPriority} from './api';
import {
  allowedVerificationUpdates,
  hasMappableLocation,
  isGatewayReport,
  matchesFilters,
  priorityLabel,
  reportChannel,
  reportPinColour,
  ALL_FILTERS,
  CHANNEL_LABELS,
} from './reportPresentation';

describe('report presentation', () => {
  it('assigns a distinct colour to every priority including unscored', () => {
    const priorities: ReportPriority[] = ['critical', 'high', 'medium', 'low', null];
    const colours = priorities.map(reportPinColour);
    expect(new Set(colours).size).toBe(5);
    expect(priorityLabel(null)).toBe('unscored');
  });

  it('only maps reports with both finite coordinates', () => {
    const report = {location: {lat: 23.8, lng: 90.4}} as CrisisReport;
    expect(hasMappableLocation(report)).toBe(true);

    report.location.lng = null;
    expect(hasMappableLocation(report)).toBe(false);
  });

  it('only offers verification transitions allowed by the responder workflow', () => {
    expect(allowedVerificationUpdates('unverified')).toEqual(['corroborated', 'verified', 'disputed']);
    expect(allowedVerificationUpdates('corroborated')).toEqual(['verified', 'disputed']);
    expect(allowedVerificationUpdates('verified')).toEqual([]);
    expect(allowedVerificationUpdates('disputed')).toEqual([]);
  });
});

describe('report channel provenance', () => {
  const GATEWAY_HASH = 'G'.repeat(43);
  const DEVICE_HASH = 'D'.repeat(43);
  const gatewayReport = {sender_pubkey_hash: GATEWAY_HASH} as CrisisReport;
  const deviceReport = {sender_pubkey_hash: DEVICE_HASH} as CrisisReport;

  it('identifies a report signed by the current gateway identity', () => {
    expect(reportChannel(gatewayReport, GATEWAY_HASH)).toBe('gateway');
    expect(isGatewayReport(gatewayReport, GATEWAY_HASH)).toBe(true);
  });

  it('classifies a non-gateway signer as device-signed when the identity is known', () => {
    expect(reportChannel(deviceReport, GATEWAY_HASH)).toBe('device');
    expect(isGatewayReport(deviceReport, GATEWAY_HASH)).toBe(false);
  });

  it('leaves attribution unknown when the backend reports no gateway identity', () => {
    // Null, undefined (older backend that omits the field), and empty string
    // must all mean "no gateway on this deployment" rather than matching.
    for (const absent of [null, undefined, '']) {
      expect(reportChannel(gatewayReport, absent)).toBe('unknown');
      expect(isGatewayReport(gatewayReport, absent)).toBe(false);
    }
  });

  it('never claims the gateway authenticated the human sender', () => {
    // The report carries only the gateway signer hash, not the exact upstream
    // adapter and not a cryptographic identity for the human sender.
    expect(CHANNEL_LABELS.gateway).toBe('Gateway-attested');
    expect(CHANNEL_LABELS.gateway.toLowerCase()).not.toContain('sms');
    expect(CHANNEL_LABELS.gateway.toLowerCase()).not.toContain('ussd');
    expect(CHANNEL_LABELS.gateway.toLowerCase()).not.toContain('verified');
  });
});

describe('responder filter composition', () => {
  const GATEWAY_HASH = 'G'.repeat(43);

  function makeReport(overrides: Partial<CrisisReport> = {}): CrisisReport {
    return {
      type: 'SOS',
      sender_pubkey_hash: 'D'.repeat(43),
      priority: 'critical',
      verification: {status: 'unverified', corroboration_count: 0},
      ...overrides,
    } as CrisisReport;
  }

  it('keeps every report when no filter is narrowed', () => {
    expect(matchesFilters(makeReport(), ALL_FILTERS, GATEWAY_HASH)).toBe(true);
  });

  it('narrows by channel in both directions', () => {
    const gatewayReport = makeReport({sender_pubkey_hash: GATEWAY_HASH});
    const deviceReport = makeReport();

    expect(matchesFilters(gatewayReport, {...ALL_FILTERS, channel: 'gateway'}, GATEWAY_HASH)).toBe(true);
    expect(matchesFilters(deviceReport, {...ALL_FILTERS, channel: 'gateway'}, GATEWAY_HASH)).toBe(false);
    expect(matchesFilters(deviceReport, {...ALL_FILTERS, channel: 'device'}, GATEWAY_HASH)).toBe(true);
    expect(matchesFilters(gatewayReport, {...ALL_FILTERS, channel: 'device'}, GATEWAY_HASH)).toBe(false);
  });

  it('requires every active filter to match, not merely one', () => {
    const report = makeReport({sender_pubkey_hash: GATEWAY_HASH, type: 'SOS'});

    // Right channel but wrong type must still be excluded.
    expect(
      matchesFilters(report, {...ALL_FILTERS, channel: 'gateway', type: 'MEDICAL_NEED'}, GATEWAY_HASH),
    ).toBe(false);
    expect(
      matchesFilters(report, {...ALL_FILTERS, channel: 'gateway', type: 'SOS'}, GATEWAY_HASH),
    ).toBe(true);
  });

  it('treats unscored priority as its own selectable state', () => {
    const unscored = makeReport({priority: null});

    expect(matchesFilters(unscored, {...ALL_FILTERS, priority: 'unscored'}, GATEWAY_HASH)).toBe(true);
    expect(matchesFilters(unscored, {...ALL_FILTERS, priority: 'critical'}, GATEWAY_HASH)).toBe(false);
    expect(matchesFilters(makeReport(), {...ALL_FILTERS, priority: 'unscored'}, GATEWAY_HASH)).toBe(false);
  });

  it('narrows by verification state', () => {
    const report = makeReport({verification: {status: 'verified', corroboration_count: 2}});

    expect(matchesFilters(report, {...ALL_FILTERS, verification: 'verified'}, GATEWAY_HASH)).toBe(true);
    expect(matchesFilters(report, {...ALL_FILTERS, verification: 'disputed'}, GATEWAY_HASH)).toBe(false);
  });

  it('does not invent gateway or device attribution when identity is unavailable', () => {
    const report = makeReport({sender_pubkey_hash: GATEWAY_HASH});

    expect(matchesFilters(report, {...ALL_FILTERS, channel: 'gateway'}, null)).toBe(false);
    expect(matchesFilters(report, {...ALL_FILTERS, channel: 'device'}, null)).toBe(false);
    expect(matchesFilters(report, {...ALL_FILTERS, channel: 'unknown'}, null)).toBe(true);
  });
});
