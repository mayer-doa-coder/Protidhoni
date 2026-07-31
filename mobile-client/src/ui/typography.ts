import {Platform} from 'react-native';

import type {AppLanguage} from '../i18n/translations';

/**
 * Android resolves bundled font assets by filename; iOS resolves the
 * typographic family stored inside each variable TTF.
 */
export function fontFamilyForLanguage(language: AppLanguage): string {
  if (language === 'bn') {
    return Platform.OS === 'ios' ? 'Anek Bangla' : 'AnekBangla';
  }
  return Platform.OS === 'ios' ? 'Anek Latin' : 'AnekLatin';
}
