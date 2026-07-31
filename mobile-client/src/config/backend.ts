import AsyncStorage from '@react-native-async-storage/async-storage';
import { NativeModules, Platform } from 'react-native';

const STORAGE_KEY = 'protidhoni.backend-origin.v1';

/** Carries a translation key, not final English text, so every caller can
 * render this in the user's current app language instead of always English
 * (see App.tsx's MeshScreen, which is the only UI-facing catch site). */
export class BackendOriginError extends Error {
  constructor(public readonly reasonKey: 'invalidUrl' | 'invalidOrigin') {
    super(reasonKey);
  }
}

export function normalizeBackendOrigin(value: string): string {
  const candidate = value.trim().replace(/\/$/, '');
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new BackendOriginError('invalidUrl');
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
    throw new BackendOriginError('invalidOrigin');
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
