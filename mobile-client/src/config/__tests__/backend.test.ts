import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  inferDevelopmentBackendOrigin,
  loadBackendOrigin,
  normalizeBackendOrigin,
  saveBackendOrigin,
} from '../backend';

beforeEach(async () => {
  await AsyncStorage.clear();
});

test('infers the backend host from the Metro development URL', () => {
  expect(inferDevelopmentBackendOrigin('http://192.168.1.42:8081/index.bundle', 'android')).toBe(
    'http://192.168.1.42:8000',
  );
});

test('uses the emulator alias when no Metro URL is available on Android', () => {
  expect(inferDevelopmentBackendOrigin('assets://index.android.bundle', 'android')).toBe(
    'http://10.0.2.2:8000',
  );
});

test.each([
  'ftp://example.test',
  'http://user:password@example.test:8000',
  'http://example.test:8000/reports',
  'http://example.test:8000?token=secret',
])('rejects an unsafe or non-origin backend URL: %s', value => {
  expect(() => normalizeBackendOrigin(value)).toThrow();
});

test('persists a normalized backend origin', async () => {
  expect(await saveBackendOrigin(' http://192.168.1.42:8000/ ')).toBe(
    'http://192.168.1.42:8000',
  );
  expect(await loadBackendOrigin('http://10.0.2.2:8000')).toBe(
    'http://192.168.1.42:8000',
  );
});

test('discards a legacy invalid stored URL and returns the safe fallback', async () => {
  await AsyncStorage.setItem('protidhoni.backend-origin.v1', `java${'script'}:alert(1)`);
  expect(await loadBackendOrigin('http://10.0.2.2:8000')).toBe('http://10.0.2.2:8000');
});
