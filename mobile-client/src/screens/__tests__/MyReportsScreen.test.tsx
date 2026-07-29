import * as React from 'react';
import {create, act} from 'react-test-renderer';

jest.mock('@op-engineering/op-sqlite', () => {
  const rows: unknown[] = [];
  return {
    open: jest.fn(() => ({
      execute: jest.fn(async (sql: string) => {
        if (sql.trim().toUpperCase().startsWith('SELECT')) {
          return {rows, rowsAffected: 0};
        }
        return {rows: [], rowsAffected: 0};
      }),
    })),
  };
});

import {MyReportsScreen} from '../MyReportsScreen';

test('renders the empty my-reports view without crashing', async () => {
  await act(async () => {
    create(<MyReportsScreen />);
  });
});
