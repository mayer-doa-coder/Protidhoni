import {afterEach, describe, expect, it, vi} from 'vitest';

import {getApiHealth, getReports, translateReport, updateReportVerification} from './api';

afterEach(() => vi.unstubAllGlobals());

describe('dashboard API client', () => {
  it('loads reports through the same-origin proxy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({reports: [], next_since: null}), {status: 200}),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getReports()).resolves.toEqual({reports: [], next_since: null});
    expect(fetchMock).toHaveBeenCalledWith('/api/reports?limit=200', {
      signal: undefined,
      cache: 'no-store',
    });
  });

  it('surfaces non-successful backend responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, {status: 503})));

    await expect(getApiHealth()).rejects.toThrow('Backend request failed (503).');
  });

  it('rejects malformed report collections', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({reports: null}), {status: 200})),
    );

    await expect(getReports()).rejects.toThrow('invalid report collection');
  });

  it('sends a responder-entered token only for an authorized verification patch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({message_id: 'report id'}), {status: 200}),
    );
    vi.stubGlobal('fetch', fetchMock);

    await updateReportVerification(
      'report id',
      {status: 'corroborated', responder_note: 'Confirmed from two sources'},
      ' responder-token ',
    );

    expect(fetchMock).toHaveBeenCalledWith('/api/reports/report%20id', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-Responder-Token': 'responder-token'},
      body: JSON.stringify({status: 'corroborated', responder_note: 'Confirmed from two sources'}),
      cache: 'no-store',
    });
  });

  it('does not send a patch without a responder token', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(updateReportVerification('id', {status: 'verified'}, '   ')).rejects.toThrow(
      'Enter the responder token',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requests a report translation with the responder token and report identifier', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({message_id: 'report id', text: 'Translated'}), {status: 200}),
    );
    vi.stubGlobal('fetch', fetchMock);

    await translateReport('report id', 'en', ' responder-token ');

    expect(fetchMock).toHaveBeenCalledWith('/api/translations', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Responder-Token': 'responder-token'},
      body: JSON.stringify({message_id: 'report id', target_language: 'en'}),
      cache: 'no-store',
    });
  });

  it('does not submit text or make a translation request without a responder token', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(translateReport('id', 'bn', '   ')).rejects.toThrow('Enter the responder token');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
