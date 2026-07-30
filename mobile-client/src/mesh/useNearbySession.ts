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
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [endpoints, setEndpoints] = useState<Record<string, string>>({});
  const [connectedPeers, setConnectedPeers] = useState<Record<string, string>>({});
  const [pendingRequests, setPendingRequests] = useState<
    Record<string, { name: string; authenticationDigits: string }>
  >({});
  const [statusMessage, setStatusMessage] = useState('Discovery stopped');
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
        setStatusMessage(`Confirm the connection with ${request.name}.`);
      },
    );
    const connected = NearbyConnections.onConnected(({ endpointId }) => {
      const name = peerNames.current[endpointId] ?? `Peer ${endpointId.slice(0, 8)}`;
      setActive(true);
      setConnectedPeers(current => ({ ...current, [endpointId]: name }));
      setPendingRequests(current => withoutKey(current, endpointId));
      setStatusMessage(`Connected to ${name}.`);
    });
    const disconnected = NearbyConnections.onDisconnected(({ endpointId }) => {
      const name = peerNames.current[endpointId] ?? 'peer';
      setConnectedPeers(current => withoutKey(current, endpointId));
      setPendingRequests(current => withoutKey(current, endpointId));
      setStatusMessage(`Disconnected from ${name}. Discovery is still running.`);
    });
    const connectionFailed = NearbyConnections.onConnectionFailed(
      ({ endpointId, statusCode }) => {
        const name = peerNames.current[endpointId] ?? 'peer';
        clearTransientPeer(endpointId);
        setConnectedPeers(current => withoutKey(current, endpointId));
        setStatusMessage(
          statusCode === 8011
            ? `${name} was no longer available. Discovery will retry when it reappears.`
            : `Could not connect to ${name} (status ${statusCode}).`,
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
          'Permission needed',
          'Nearby discovery cannot start until all requested nearby-device permissions are allowed.',
        );
        return;
      }
      await NearbyConnections.start(endpointName);
      setActive(true);
      setStatusMessage(`Advertising as ${endpointName}.`);
    } catch (error) {
      Alert.alert(
        'Nearby unavailable',
        error instanceof Error ? error.message : 'Unable to start discovery.',
      );
    } finally {
      setStarting(false);
    }
  }, [active, starting]);

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
      setStatusMessage('Discovery stopped');
    }
  }, []);

  const respond = useCallback(async (endpointId: string, accept: boolean) => {
    setPendingRequests(current => withoutKey(current, endpointId));
    try {
      await NearbyConnections.respondToConnection(endpointId, accept);
      if (!accept) setStatusMessage('Connection request declined.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      Alert.alert(
        'Peer no longer available',
        message.includes('8011') || message.includes('STATUS_ENDPOINT_UNKNOWN')
          ? 'The other phone stopped advertising or moved out of range. Keep discovery running on both phones and try again.'
          : `Could not respond to the connection request: ${message}`,
      );
    }
  }, []);

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
