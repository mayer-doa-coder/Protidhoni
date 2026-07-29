import type {CrisisReport} from '../contracts/report';
import type {ReportDraft} from '../crypto/sign';
import {getReportFormConfig, type CreatableReportType} from './reportFormConfig';

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

function invalid(title: string, message: string): BuildReportDraftResult {
  return {ok: false, error: {title, message}};
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

export function buildReportDraft(values: ReportFormValues): BuildReportDraftResult {
  const text = values.text.trim();
  if (text.length === 0) {
    return invalid('Description required', 'Describe the situation before saving the report.');
  }
  if (text.length > 2000) {
    return invalid('Description too long', 'Keep the description at 2,000 characters or fewer.');
  }

  let peopleCount: number | null = null;
  const peopleText = values.peopleCount.trim();
  if (peopleText !== '') {
    if (!/^\d+$/.test(peopleText)) {
      return invalid('People count invalid', 'Enter a whole number between 1 and 100,000.');
    }
    peopleCount = Number(peopleText);
    if (!Number.isSafeInteger(peopleCount) || peopleCount < 1 || peopleCount > 100_000) {
      return invalid('People count invalid', 'Enter a whole number between 1 and 100,000.');
    }
  }

  const config = getReportFormConfig(values.type);
  const allowedNeeds = new Set(config.needs.map(need => need.value));
  const uniqueNeeds = [...new Set(values.needs)];
  if (uniqueNeeds.length !== values.needs.length || uniqueNeeds.some(need => !allowedNeeds.has(need))) {
    return invalid('Selection invalid', 'Choose needs from the options shown for this report type.');
  }

  const location = buildLocation(values.location);
  if (location === null) {
    return invalid(
      'Location invalid',
      'Use valid latitude/longitude values, valid GPS accuracy, or choose no location.',
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
