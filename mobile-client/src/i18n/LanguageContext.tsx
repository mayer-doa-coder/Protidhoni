import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import {
  translate,
  type AppLanguage,
  type TranslationKey,
  type TranslationParams,
} from './translations';
import {fontFamilyForLanguage} from '../ui/typography';

const LANGUAGE_STORAGE_KEY = '@protidhoni/app-language';

type LanguageContextValue = {
  language: AppLanguage;
  fontFamily: string;
  setLanguage(language: AppLanguage): void;
  toggleLanguage(): void;
  t(key: TranslationKey, params?: TranslationParams): string;
  formatNumber(value: number): string;
  formatDate(value: string): string;
};

function makeFallbackContext(): LanguageContextValue {
  return {
    language: 'en',
    fontFamily: fontFamilyForLanguage('en'),
    setLanguage: () => undefined,
    toggleLanguage: () => undefined,
    t: (key, params) => translate('en', key, params),
    formatNumber: value => String(value),
    formatDate: value => new Date(value).toLocaleString('en-BD'),
  };
}

const LanguageContext = createContext<LanguageContextValue>(makeFallbackContext());

export function LanguageProvider({children}: {children: ReactNode}) {
  const [language, setLanguageState] = useState<AppLanguage>('en');

  useEffect(() => {
    let cancelled = false;
    // Loading failure is non-fatal: English remains the deterministic default.
    // eslint-disable-next-line no-void -- effects cannot await
    void AsyncStorage.getItem(LANGUAGE_STORAGE_KEY)
      .then(stored => {
        if (!cancelled && (stored === 'en' || stored === 'bn')) {
          setLanguageState(stored);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const setLanguage = useCallback((nextLanguage: AppLanguage) => {
    setLanguageState(nextLanguage);
    // The UI changes immediately; persistence is best-effort for the next launch.
    // eslint-disable-next-line no-void -- event handlers should not wait on storage
    void AsyncStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage).catch(
      () => undefined,
    );
  }, []);

  const toggleLanguage = useCallback(() => {
    setLanguage(language === 'en' ? 'bn' : 'en');
  }, [language, setLanguage]);

  const t = useCallback(
    (key: TranslationKey, params?: TranslationParams) =>
      translate(language, key, params),
    [language],
  );

  const locale = language === 'bn' ? 'bn-BD' : 'en-BD';
  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      fontFamily: fontFamilyForLanguage(language),
      setLanguage,
      toggleLanguage,
      t,
      formatNumber: number =>
        new Intl.NumberFormat(locale, {maximumFractionDigits: 5}).format(number),
      formatDate: raw => new Date(raw).toLocaleString(locale),
    }),
    [language, locale, setLanguage, t, toggleLanguage],
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}

export {LANGUAGE_STORAGE_KEY};
