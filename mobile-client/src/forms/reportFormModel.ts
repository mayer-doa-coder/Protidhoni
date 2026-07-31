import type {CrisisReport} from '../contracts/report';
import type {ReportDraft} from '../crypto/sign';
import {getReportFormConfig, type CreatableReportType} from './reportFormConfig';
import {
  translate,
  type AppLanguage,
  type TranslationKey,
} from '../i18n/translations';

export type FormLocationInput =
  | {source: 'none'}
  | {source: 'gps'; lat: number; lng: number; accuracyM: number}
  | {source: 'manual'; lat: string; lng: string};

export type ReportFormValues = {
  type: CreatableReportType;
  language: CrisisReport['language'];
  text: string;
  peopleCount: string;
  needs: readonly string[];
  location: FormLocationInput;
};

export type FormValidationError = {
  title: string;
  message: string;
};

export type BuildReportDraftResult =
  | {ok: true; draft: ReportDraft}
  | {ok: false; error: FormValidationError};

function invalid(
  language: AppLanguage,
  titleKey: TranslationKey,
  messageKey: TranslationKey,
): BuildReportDraftResult {
  return {
    ok: false,
    error: {
      title: translate(language, titleKey),
      message: translate(language, messageKey),
    },
  };
}

function buildLocation(location: FormLocationInput): CrisisReport['location'] | null {
  if (location.source === 'none') {
    return {lat: null, lng: null, accuracy_m: null, source: 'none'};
  }

  const lat = location.source === 'manual' ? Number(location.lat.trim()) : location.lat;
  const lng = location.source === 'manual' ? Number(location.lng.trim()) : location.lng;
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    return null;
  }

  if (location.source === 'manual') {
    if (location.lat.trim() === '' || location.lng.trim() === '') return null;
    return {lat, lng, accuracy_m: null, source: 'manual'};
  }

  if (!Number.isFinite(location.accuracyM) || location.accuracyM <= 0) return null;
  return {lat, lng, accuracy_m: location.accuracyM, source: 'gps'};
}

export function buildReportDraft(
  values: ReportFormValues,
  displayLanguage: AppLanguage = 'en',
): BuildReportDraftResult {
  const text = values.text.trim();
  if (text.length === 0) {
    return invalid(
      displayLanguage,
      'validation.descriptionRequired.title',
      'validation.descriptionRequired.message',
    );
  }
  if (text.length > 2000) {
    return invalid(
      displayLanguage,
      'validation.descriptionLong.title',
      'validation.descriptionLong.message',
    );
  }

  let peopleCount: number | null = null;
  const peopleText = values.peopleCount.trim();
  if (peopleText !== '') {
    if (!/^\d+$/.test(peopleText)) {
      return invalid(
        displayLanguage,
        'validation.peopleInvalid.title',
        'validation.peopleInvalid.message',
      );
    }
    peopleCount = Number(peopleText);
    if (!Number.isSafeInteger(peopleCount) || peopleCount < 1 || peopleCount > 100_000) {
      return invalid(
        displayLanguage,
        'validation.peopleInvalid.title',
        'validation.peopleInvalid.message',
      );
    }
  }

  const config = getReportFormConfig(values.type);
  const allowedNeeds = new Set(config.needs.map(need => need.value));
  const uniqueNeeds = [...new Set(values.needs)];
  if (uniqueNeeds.length !== values.needs.length || uniqueNeeds.some(need => !allowedNeeds.has(need))) {
    return invalid(
      displayLanguage,
      'validation.selectionInvalid.title',
      'validation.selectionInvalid.message',
    );
  }

  const location = buildLocation(values.location);
  if (location === null) {
    return invalid(
      displayLanguage,
      'validation.locationInvalid.title',
      'validation.locationInvalid.message',
    );
  }

  return {
    ok: true,
    draft: {
      type: values.type,
      language: values.language,
      location,
      payload: {
        text,
        people_count: peopleCount,
        needs: uniqueNeeds,
        attachment_ref: null,
      },
    },
  };
}
