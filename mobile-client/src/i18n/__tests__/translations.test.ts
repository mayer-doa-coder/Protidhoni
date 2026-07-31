import {translate, translations} from '../translations';

describe('application translations', () => {
  it('keeps the English and Bangla catalogs structurally identical', () => {
    expect(Object.keys(translations.bn).sort()).toEqual(
      Object.keys(translations.en).sort(),
    );
  });

  it('interpolates dynamic values without leaving template markers', () => {
    expect(
      translate('bn', 'connection.active', {count: '২'}),
    ).toBe('কাছাকাছি সংযোগ চালু • ২ জন সংযুক্ত');
    expect(
      translate('en', 'mesh.connectQuestion', {name: 'Protidhoni-a1'}),
    ).toBe('Connect with Protidhoni-a1?');
  });

  it('contains Bangla script in every non-technical Bangla message', () => {
    const technicalKeys = new Set([
      'language.english',
      'mesh.backend.help',
      'mesh.backend.url',
      'report.location.gpsSummary',
    ]);
    const missingBangla = Object.entries(translations.bn)
      .filter(([key]) => !technicalKeys.has(key))
      .filter(([, value]) => !/[\u0980-\u09ff]/.test(value))
      .map(([key]) => key);
    expect(missingBangla).toEqual([]);
  });
});
