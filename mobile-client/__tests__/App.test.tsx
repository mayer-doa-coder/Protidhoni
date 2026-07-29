import * as React from 'react';
import {create} from 'react-test-renderer';

jest.mock('../src/native/NearbyConnections', () => ({
  NearbyConnections: {
    start: jest.fn(),
    stop: jest.fn(),
    onEndpointFound: jest.fn(() => ({remove: jest.fn()})),
    onEndpointLost: jest.fn(() => ({remove: jest.fn()})),
  },
}));

import App from '../App';

test('renders the Phase 0 discovery boundary', () => {
  create(<App />);
});
