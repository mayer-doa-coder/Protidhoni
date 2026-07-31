import * as React from 'react';
import {act, create, type ReactTestRenderer} from 'react-test-renderer';
import {Alert, PermissionsAndroid, Platform} from 'react-native';

jest.mock('@react-native-community/geolocation', () => ({
  getCurrentPosition: jest.fn(),
}));

jest.mock('@op-engineering/op-sqlite', () => ({
  open: jest.fn(() => ({
    execute: jest.fn(async () => ({rows: [], rowsAffected: 0})),
  })),
}));

// identity.ts (imported transitively via ../ReportFormScreen -> crypto/sign)
// wraps the device key via the native KeystoreWrap module; see
// src/native/__mocks__/KeystoreWrap.ts.
jest.mock('../../native/KeystoreWrap');

import {REPORT_FORM_CONFIGS} from '../../forms/reportFormConfig';
import {LanguageProvider} from '../../i18n/LanguageContext';
import {ReportFormScreen} from '../ReportFormScreen';

test('renders every configured report type from the reusable form', async () => {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(<ReportFormScreen />);
  });

  for (const config of REPORT_FORM_CONFIGS) {
    const selector = renderer!.root.findByProps({testID: `report-type-${config.type}`});
    await act(async () => selector.props.onPress());
    const visibleText = renderer!.root
      .findAll(node => typeof node.props.children === 'string')
      .map(node => node.props.children);
    expect(visibleText).toContain(config.label);
    for (const need of config.needs) {
      expect(renderer!.root.findByProps({testID: `report-need-${need.value}`})).toBeDefined();
    }
  }

  await act(async () => renderer!.unmount());
});

test('the form language control translates all configuration-driven labels', async () => {
  let renderer: ReactTestRenderer | undefined;
  await act(async () => {
    renderer = create(
      <LanguageProvider>
        <ReportFormScreen />
      </LanguageProvider>,
    );
  });

  await act(async () => {
    renderer!.root.findByProps({testID: 'report-language-bn'}).props.onPress();
  });

  const visibleText = renderer!.root
    .findAll(node => typeof node.props.children === 'string')
    .map(node => node.props.children);
  expect(visibleText).toContain('প্রতিবেদন তৈরি করুন');
  expect(visibleText).toContain('জরুরি এসওএস');
  expect(visibleText).toContain('উদ্ধার');

  await act(async () => renderer!.unmount());
});

test('surfaces an Android location-permission failure without an unhandled rejection', async () => {
  const platformReplacement = jest.replaceProperty(Platform, 'OS', 'android');
  const permissionSpy = jest
    .spyOn(PermissionsAndroid, 'request')
    .mockRejectedValueOnce(new Error('permission service unavailable'));
  const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  let renderer: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      renderer = create(<ReportFormScreen />);
    });
    await act(async () => {
      renderer!.root.findByProps({testID: 'report-location-gps'}).props.onPress();
      await Promise.resolve();
    });
    expect(alertSpy).toHaveBeenCalledWith(
      'Location permission unavailable',
      'permission service unavailable',
    );
  } finally {
    if (renderer) await act(async () => renderer!.unmount());
    platformReplacement.restore();
    permissionSpy.mockRestore();
    alertSpy.mockRestore();
  }
});
