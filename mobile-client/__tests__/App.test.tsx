import * as React from 'react';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { Text } from 'react-native';

// Self-contained factory (see relay.test.ts's comment on the Babel hoisting
// hazard): captures the connectionRequested listener so tests can trigger it
// directly, the same way relay.test.ts captures onConnected/onPayloadReceived.
jest.mock('../src/native/NearbyConnections', () => {
  const connectionRequested: Array<
    (request: {
      endpointId: string;
      name: string;
      authenticationDigits: string;
    }) => void
  > = [];
  return {
    NearbyConnections: {
      start: jest.fn(),
      stop: jest.fn(),
      sendPayload: jest.fn(),
      onEndpointFound: jest.fn(() => ({ remove: jest.fn() })),
      onEndpointLost: jest.fn(() => ({ remove: jest.fn() })),
      onConnected: jest.fn(() => ({ remove: jest.fn() })),
      onDisconnected: jest.fn(() => ({ remove: jest.fn() })),
      onPayloadReceived: jest.fn(() => ({ remove: jest.fn() })),
      onConnectionRequested: (
        listener: (request: {
          endpointId: string;
          name: string;
          authenticationDigits: string;
        }) => void,
      ) => {
        connectionRequested.push(listener);
        return { remove: jest.fn() };
      },
      respondToConnection: jest.fn(async () => undefined),
      __mockListeners: { connectionRequested },
    },
  };
});

jest.mock('@op-engineering/op-sqlite', () => ({
  open: jest.fn(() => ({
    execute: jest.fn(async () => ({ rows: [], rowsAffected: 0 })),
  })),
}));

jest.mock('@react-native-community/netinfo', () => ({
  __esModule: true,
  default: { addEventListener: jest.fn(() => jest.fn()) },
}));

jest.mock('@react-native-community/geolocation', () => ({
  getCurrentPosition: jest.fn(),
}));

// identity.ts (imported transitively via ../App -> mesh/relay) wraps the
// device key via the native KeystoreWrap module; see
// src/native/__mocks__/KeystoreWrap.ts.
jest.mock('../src/native/KeystoreWrap');

// SafeAreaProvider renders `children: null` under Jest without a mock (no
// real native safe-area insets exist in the test environment). The
// package ships an official jest mock, but it's untransformed ESM/TSX and
// outside this project's transformIgnorePatterns allow-list; a plain
// passthrough is simpler than widening that shared, project-global config.
jest.mock('react-native-safe-area-context', () => ({
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
  SafeAreaView: ({ children }: { children: React.ReactNode }) => children,
}));

import App from '../App';
import { NearbyConnections } from '../src/native/NearbyConnections';

type MockedNearbyConnections = typeof NearbyConnections & {
  __mockListeners: {
    connectionRequested: Array<
      (request: {
        endpointId: string;
        name: string;
        authenticationDigits: string;
      }) => void
    >;
  };
};

const mockListeners = (NearbyConnections as MockedNearbyConnections)
  .__mockListeners;
const mockRespondToConnection =
  NearbyConnections.respondToConnection as jest.MockedFunction<
    typeof NearbyConnections.respondToConnection
  >;

beforeEach(() => {
  mockListeners.connectionRequested.length = 0;
  mockRespondToConnection.mockClear();
});

test('renders the app (Create tab by default) without crashing', async () => {
  await act(async () => {
    create(<App />);
  });
});

test('shows an incoming Nearby connection request and lets the user accept it', async () => {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<App />);
  });

  await act(async () => {
    renderer!.root.findByProps({ testID: 'tab-mesh' }).props.onPress();
  });

  await act(async () => {
    mockListeners.connectionRequested[0]({
      endpointId: 'peer-1',
      name: 'Protidhoni-abcxyz',
      authenticationDigits: '123456',
    });
  });

  expect(
    renderer!.root.findAllByType(Text).some(node => {
      const children = node.props.children;
      const text = Array.isArray(children) ? children.join('') : children;
      return text === 'Connect with Protidhoni-abcxyz?';
    }),
  ).toBe(true);
  expect(
    renderer!.root.findAllByType(Text).some(node => {
      const children = node.props.children;
      const text = Array.isArray(children) ? children.join('') : children;
      return text === 'Confirm digits: 123456';
    }),
  ).toBe(true);

  await act(async () => {
    renderer!.root.findByProps({ testID: 'accept-peer-1' }).props.onPress();
  });

  expect(mockRespondToConnection).toHaveBeenCalledWith('peer-1', true);
  expect(
    renderer!.root.findAllByProps({ testID: 'accept-peer-1' }),
  ).toHaveLength(0);
});

test('lets the user decline an incoming Nearby connection request', async () => {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<App />);
  });

  await act(async () => {
    renderer!.root.findByProps({ testID: 'tab-mesh' }).props.onPress();
  });

  await act(async () => {
    mockListeners.connectionRequested[0]({
      endpointId: 'peer-2',
      name: 'Protidhoni-zzz',
      authenticationDigits: '654321',
    });
  });

  await act(async () => {
    renderer!.root.findByProps({ testID: 'decline-peer-2' }).props.onPress();
  });

  expect(mockRespondToConnection).toHaveBeenCalledWith('peer-2', false);
  expect(
    renderer!.root.findAllByProps({ testID: 'decline-peer-2' }),
  ).toHaveLength(0);
});
