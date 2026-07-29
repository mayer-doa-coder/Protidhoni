import * as React from 'react';
import {act, create} from 'react-test-renderer';

jest.mock('../src/native/NearbyConnections', () => ({
  NearbyConnections: {
    start: jest.fn(),
    stop: jest.fn(),
    sendPayload: jest.fn(),
    onEndpointFound: jest.fn(() => ({remove: jest.fn()})),
    onEndpointLost: jest.fn(() => ({remove: jest.fn()})),
    onConnected: jest.fn(() => ({remove: jest.fn()})),
    onDisconnected: jest.fn(() => ({remove: jest.fn()})),
    onPayloadReceived: jest.fn(() => ({remove: jest.fn()})),
  },
}));

jest.mock('@op-engineering/op-sqlite', () => ({
  open: jest.fn(() => ({
    execute: jest.fn(async () => ({rows: [], rowsAffected: 0})),
  })),
}));

jest.mock('@react-native-community/netinfo', () => ({
  __esModule: true,
  default: {addEventListener: jest.fn(() => jest.fn())},
}));

jest.mock('@react-native-community/geolocation', () => ({
  getCurrentPosition: jest.fn(),
}));

import App from '../App';

test('renders the app (Create tab by default) without crashing', async () => {
  await act(async () => {
    create(<App />);
  });
});
