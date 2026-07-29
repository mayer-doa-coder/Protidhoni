import * as React from 'react';
import {create} from 'react-test-renderer';

jest.mock('@react-native-community/geolocation', () => ({
  getCurrentPosition: jest.fn(),
}));

jest.mock('@op-engineering/op-sqlite', () => ({
  open: jest.fn(() => ({
    execute: jest.fn(async () => ({rows: [], rowsAffected: 0})),
  })),
}));

import {SosFormScreen} from '../SosFormScreen';

test('renders the SOS form without crashing', () => {
  create(<SosFormScreen />);
});
