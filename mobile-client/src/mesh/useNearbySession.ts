import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  type Permission,
} from 'react-native';

import {
  NearbyConnections,
  type ConnectionRequest,
  type Endpoint,
} from '../native/NearbyConnections';
import {useLanguage} from '../i18n/LanguageContext';
import type {
  TranslationKey,
  TranslationParams,
} from '../i18n/translations';

const endpointName = `Protidhoni-${Math.random().toString(36).slice(2, 8)}`;

async function requestNearbyPermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;

  const permissions: Permission[] = [];
  if (Platform.Version >= 31) {
    permissions.push(
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_ADVERTISE,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
    );
  } else if (Platform.Version >= 29) {
    permissions.push(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  }
  if (
    Platform.Version >= 33 &&
    PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES
  ) {
    permissions.push(PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES);
  }

  const results = await PermissionsAndroid.requestMultiple(permissions);
  return permissions.every(
    permission => results[permission] === PermissionsAndroid.RESULTS.GRANTED,
  );
}

export type NearbySession = {
  active: boolean;
  starting: boolean;
  endpointName: string;
  endpoints: Record<string, string>;
  connectedPeers: Record<string, string>;
  pendingRequests: Record<
    string,
    { name: string; authenticationDigits: string }
  >;
  statusMessage: string;
  start(): Promise<void>;
  stop(): Promise<void>;
  respond(endpointId: string, accept: boolean): Promise<void>;
};

function withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  if (!(key in record)) return record;
  const next = { ...record };
  delete next[key];
  return next;
}

/** Owns the Nearby session for the lifetime of the app, not the Nearby tab. */
export function useNearbySession(): NearbySession {
  const {t} = useLanguage();
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [endpoints, setEndpoints] = useState<Record<string, string>>({});
  const [connectedPeers, setConnectedPeers] = useState<Record<string, string>>({});
  const [pendingRequests, setPendingRequests] = useState<
    Record<string, { name: string; authenticationDigits: string }>
  >({});
  const [status, setStatus] = useState<{
    key: TranslationKey;
    params?: TranslationParams;
  }>({key: 'nearby.status.stopped'});
  const peerNames = useRef<Record<string, string>>({});

  const clearTransientPeer = useCallback((endpointId: string) => {
    setEndpoints(current => withoutKey(current, endpointId));
    setPendingRequests(current => withoutKey(current, endpointId));
  }, []);

  useEffect(() => {
    const found = NearbyConnections.onEndpointFound((endpoint: Endpoint) => {
      peerNames.current[endpoint.endpointId] = endpoint.name;
      setEndpoints(current => ({
        ...current,
        [endpoint.endpointId]: endpoint.name,
      }));
      setConnectedPeers(current =>
        endpoint.endpointId in current
          ? { ...current, [endpoint.endpointId]: endpoint.name }
          : current,
      );
    });
    const lost = NearbyConnections.onEndpointLost(({ endpointId }) => {
      setEndpoints(current => withoutKey(current, endpointId));
    });
    const requested = NearbyConnections.onConnectionRequested(
      (request: ConnectionRequest) => {
        peerNames.current[request.endpointId] = request.name;
        setPendingRequests(current => ({
          ...current,
          [request.endpointId]: {
            name: request.name,
            authenticationDigits: request.authenticationDigits,
          },
        }));
        setStatus({key: 'nearby.status.confirm', params: {name: request.name}});
      },
    );
    const connected = NearbyConnections.onConnected(({ endpointId }) => {
      const name =
        peerNames.current[endpointId] ??
        endpointId.slice(0, 8);
      setActive(true);
      setConnectedPeers(current => ({ ...current, [endpointId]: name }));
      setPendingRequests(current => withoutKey(current, endpointId));
      setStatus({key: 'nearby.status.connected', params: {name}});
    });
    const disconnected = NearbyConnections.onDisconnected(({ endpointId }) => {
      const name = peerNames.current[endpointId] ?? endpointId.slice(0, 8);
      setConnectedPeers(current => withoutKey(current, endpointId));
      setPendingRequests(current => withoutKey(current, endpointId));
      setStatus({key: 'nearby.status.disconnected', params: {name}});
    });
    const connectionFailed = NearbyConnections.onConnectionFailed(
      ({ endpointId, statusCode }) => {
        const name = peerNames.current[endpointId] ?? endpointId.slice(0, 8);
        clearTransientPeer(endpointId);
        setConnectedPeers(current => withoutKey(current, endpointId));
        setStatus(
          statusCode === 8011
            ? {key: 'nearby.status.stale', params: {name}}
            : {
                key: 'nearby.status.failed',
                params: {name, status: statusCode},
              },
        );
      },
    );

    return () => {
      found.remove();
      lost.remove();
      requested.remove();
      connected.remove();
      disconnected.remove();
      connectionFailed.remove();
      // eslint-disable-next-line no-void -- React effect cleanup cannot await
      void NearbyConnections.stop().catch(() => undefined);
    };
  }, [clearTransientPeer]);

  const start = useCallback(async () => {
    if (active || starting) return;
    setStarting(true);
    try {
      if (!(await requestNearbyPermissions())) {
        Alert.alert(
          t('nearby.permission.title'),
          t('nearby.permission.message'),
        );
        return;
      }
      await NearbyConnections.start(endpointName);
      setActive(true);
      setStatus({
        key: 'nearby.status.advertising',
        params: {name: endpointName},
      });
    } catch (error) {
      Alert.alert(
        t('nearby.unavailable.title'),
        error instanceof Error
          ? `${t('nearby.unavailable.message')}\n${error.message}`
          : t('nearby.unavailable.message'),
      );
    } finally {
      setStarting(false);
    }
  }, [active, starting, t]);

  const stop = useCallback(async () => {
    try {
      await NearbyConnections.stop();
    } finally {
      peerNames.current = {};
      setEndpoints({});
      setConnectedPeers({});
      setPendingRequests({});
      setActive(false);
      setStarting(false);
      setStatus({key: 'nearby.status.stopped'});
    }
  }, []);

  const respond = useCallback(async (endpointId: string, accept: boolean) => {
    setPendingRequests(current => withoutKey(current, endpointId));
    try {
      await NearbyConnections.respondToConnection(endpointId, accept);
      if (!accept) setStatus({key: 'nearby.status.declined'});
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      Alert.alert(
        t('nearby.peerUnavailable.title'),
        message.includes('8011') || message.includes('STATUS_ENDPOINT_UNKNOWN')
          ? t('nearby.peerUnavailable.stale')
          : t('nearby.peerUnavailable.failed', {message}),
      );
    }
  }, [t]);

  const statusMessage = t(status.key, status.params);

  return useMemo(
    () => ({
      active,
      starting,
      endpointName,
      endpoints,
      connectedPeers,
      pendingRequests,
      statusMessage,
      start,
      stop,
      respond,
    }),
    [
      active,
      connectedPeers,
      endpoints,
      pendingRequests,
      respond,
      start,
      starting,
      statusMessage,
      stop,
    ],
  );
}
