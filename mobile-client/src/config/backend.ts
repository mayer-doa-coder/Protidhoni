import AsyncStorage from '@react-native-async-storage/async-storage';
import { NativeModules, Platform } from 'react-native';

const STORAGE_KEY = 'protidhoni.backend-origin.v1';

export function normalizeBackendOrigin(value: string): string {
  const candidate = value.trim().replace(/\/$/, '');
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error('Enter a complete backend URL, for example http://192.168.1.20:8000.');
  }
  if (
    !['http:', 'https:'].includes(parsed.protocol) ||
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== '/' ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error('The backend URL must be an HTTP(S) origin without a path or credentials.');
  }
  return candidate;
}

export function inferDevelopmentBackendOrigin(
  scriptUrl: string | undefined,
  platform: string = Platform.OS,
): string {
  if (scriptUrl) {
    try {
      const metro = new URL(scriptUrl);
      if (['http:', 'https:'].includes(metro.protocol) && metro.hostname) {
        return `${metro.protocol}//${metro.hostname}:8000`;
      }
    } catch {
      // A release bundle uses an assets/file URL. Fall through to the local default.
    }
  }
  return platform === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
}

export function defaultBackendOrigin(): string {
  const sourceCode = NativeModules.SourceCode as { scriptURL?: string } | undefined;
  return inferDevelopmentBackendOrigin(sourceCode?.scriptURL);
}

export async function loadBackendOrigin(fallback: string): Promise<string> {
  const stored = await AsyncStorage.getItem(STORAGE_KEY);
  if (!stored) return fallback;
  try {
    return normalizeBackendOrigin(stored);
  } catch {
    await AsyncStorage.removeItem(STORAGE_KEY);
    return fallback;
  }
}

export async function saveBackendOrigin(value: string): Promise<string> {
  const normalized = normalizeBackendOrigin(value);
  await AsyncStorage.setItem(STORAGE_KEY, normalized);
  return normalized;
}
