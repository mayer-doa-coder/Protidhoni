import {afterEach, describe, expect, it, vi} from 'vitest';

import {getApiHealth, getReports} from './api';

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
});
