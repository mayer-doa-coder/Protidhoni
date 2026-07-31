import type {ReportType} from '../contracts/report';
import type {AppLanguage} from '../i18n/translations';

export type CreatableReportType = Exclude<ReportType, 'INSTRUCTION'>;

export type NeedOption = {
  value: string;
  label: string;
};

export type ReportFormConfig = {
  type: CreatableReportType;
  label: string;
  shortLabel: string;
  helper: string;
  descriptionLabel: string;
  descriptionPlaceholder: string;
  peopleCountLabel: string;
  needsLabel: string;
  needs: readonly NeedOption[];
};

const option = (value: string, label: string): NeedOption => ({value, label});

export const REPORT_FORM_CONFIGS: readonly ReportFormConfig[] = [
  {
    type: 'SOS',
    label: 'Emergency SOS',
    shortLabel: 'SOS',
    helper: 'Use for immediate danger or urgent rescue.',
    descriptionLabel: 'What is happening?',
    descriptionPlaceholder: 'Describe the emergency and immediate danger',
    peopleCountLabel: 'People affected (optional)',
    needsLabel: 'Immediate help needed',
    needs: [
      option('rescue', 'Rescue'),
      option('medical', 'Medical'),
      option('water', 'Water'),
      option('food', 'Food'),
      option('shelter', 'Shelter'),
    ],
  },
  {
    type: 'MEDICAL_NEED',
    label: 'Medical need',
    shortLabel: 'Medical',
    helper: 'Report injuries, illness, medicine, or evacuation needs.',
    descriptionLabel: 'What medical help is needed?',
    descriptionPlaceholder: 'Describe symptoms, injuries, and urgency without adding names',
    peopleCountLabel: 'Patients affected (optional)',
    needsLabel: 'Medical support needed',
    needs: [
      option('first_aid', 'First aid'),
      option('ambulance', 'Ambulance'),
      option('medicine', 'Medicine'),
      option('blood', 'Blood'),
      option('medical_evacuation', 'Evacuation'),
    ],
  },
  {
    type: 'RESOURCE_NEED',
    label: 'Resource need',
    shortLabel: 'Resources',
    helper: 'Request essential supplies for affected people.',
    descriptionLabel: 'What supplies are needed?',
    descriptionPlaceholder: 'Describe quantities, urgency, and who needs the supplies',
    peopleCountLabel: 'People needing supplies (optional)',
    needsLabel: 'Resources needed',
    needs: [
      option('water', 'Water'),
      option('food', 'Food'),
      option('clothing', 'Clothing'),
      option('sanitation', 'Sanitation'),
      option('power', 'Power'),
      option('fuel', 'Fuel'),
    ],
  },
  {
    type: 'SHELTER_INFO',
    label: 'Shelter information',
    shortLabel: 'Shelter',
    helper: 'Share shelter availability, capacity, or missing services.',
    descriptionLabel: 'What is the shelter situation?',
    descriptionPlaceholder: 'Describe availability, capacity, access, and current conditions',
    peopleCountLabel: 'People accommodated or waiting (optional)',
    needsLabel: 'Shelter services needed',
    needs: [
      option('water', 'Water'),
      option('food', 'Food'),
      option('medical', 'Medical'),
      option('sanitation', 'Sanitation'),
      option('accessibility', 'Accessible access'),
    ],
  },
  {
    type: 'HAZARD_UPDATE',
    label: 'Hazard update',
    shortLabel: 'Hazard',
    helper: 'Report changing flood, fire, collapse, contamination, or road danger.',
    descriptionLabel: 'What hazard did you observe?',
    descriptionPlaceholder: 'Describe the hazard, direction of spread, and nearby landmarks',
    peopleCountLabel: 'People at risk (optional)',
    needsLabel: 'Response needed',
    needs: [
      option('evacuation', 'Evacuation'),
      option('rescue', 'Rescue'),
      option('road_clearance', 'Road clearance'),
      option('fire_service', 'Fire service'),
      option('medical', 'Medical'),
    ],
  },
  {
    type: 'SAFETY_STATUS',
    label: 'Safety status',
    shortLabel: 'Safety',
    helper: 'Share whether people are safe, injured, trapped, or need evacuation.',
    descriptionLabel: 'What is the current safety status?',
    descriptionPlaceholder: 'Describe who is safe or at risk without adding unnecessary identity details',
    peopleCountLabel: 'People covered by this update (optional)',
    needsLabel: 'Help still needed',
    needs: [
      option('medical', 'Medical'),
      option('evacuation', 'Evacuation'),
      option('rescue', 'Rescue'),
      option('contact_family', 'Contact family'),
    ],
  },
  {
    type: 'SAFE_ROUTE',
    label: 'Safe route',
    shortLabel: 'Safe route',
    helper: 'Share a passable route or report what support it needs.',
    descriptionLabel: 'Where does the route go and why is it safe?',
    descriptionPlaceholder: 'Describe start, destination, landmarks, obstacles, and travel direction',
    peopleCountLabel: 'People expected to use it (optional)',
    needsLabel: 'Route support needed',
    needs: [
      option('transport', 'Transport'),
      option('road_clearance', 'Road clearance'),
      option('signage', 'Signage'),
      option('escort', 'Escort'),
      option('medical', 'Medical'),
    ],
  },
] as const;

type LocalizedFormCopy = Pick<
  ReportFormConfig,
  | 'label'
  | 'shortLabel'
  | 'helper'
  | 'descriptionLabel'
  | 'descriptionPlaceholder'
  | 'peopleCountLabel'
  | 'needsLabel'
> & {needLabels: Record<string, string>};

const BANGLA_FORM_COPY: Record<CreatableReportType, LocalizedFormCopy> = {
  SOS: {
    label: 'জরুরি এসওএস',
    shortLabel: 'এসওএস',
    helper: 'তাৎক্ষণিক বিপদ বা জরুরি উদ্ধারের জন্য ব্যবহার করুন।',
    descriptionLabel: 'কী ঘটছে?',
    descriptionPlaceholder: 'জরুরি পরিস্থিতি ও তাৎক্ষণিক বিপদের বিবরণ লিখুন',
    peopleCountLabel: 'ক্ষতিগ্রস্ত মানুষের সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'তাৎক্ষণিক যে সহায়তা প্রয়োজন',
    needLabels: {
      rescue: 'উদ্ধার', medical: 'চিকিৎসা', water: 'পানি', food: 'খাবার', shelter: 'আশ্রয়',
    },
  },
  MEDICAL_NEED: {
    label: 'চিকিৎসা সহায়তা',
    shortLabel: 'চিকিৎসা',
    helper: 'আঘাত, অসুস্থতা, ওষুধ বা চিকিৎসার জন্য স্থানান্তরের প্রয়োজন জানান।',
    descriptionLabel: 'কী চিকিৎসা সহায়তা প্রয়োজন?',
    descriptionPlaceholder: 'নাম উল্লেখ না করে উপসর্গ, আঘাত ও জরুরিতার বিবরণ লিখুন',
    peopleCountLabel: 'আক্রান্ত রোগীর সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'যে চিকিৎসা সহায়তা প্রয়োজন',
    needLabels: {
      first_aid: 'প্রাথমিক চিকিৎসা', ambulance: 'অ্যাম্বুলেন্স', medicine: 'ওষুধ', blood: 'রক্ত', medical_evacuation: 'চিকিৎসার জন্য স্থানান্তর',
    },
  },
  RESOURCE_NEED: {
    label: 'জরুরি উপকরণের প্রয়োজন',
    shortLabel: 'উপকরণ',
    helper: 'ক্ষতিগ্রস্ত মানুষের জন্য জরুরি সরবরাহের অনুরোধ করুন।',
    descriptionLabel: 'কী কী উপকরণ প্রয়োজন?',
    descriptionPlaceholder: 'পরিমাণ, জরুরিতা এবং কাদের জন্য প্রয়োজন তা লিখুন',
    peopleCountLabel: 'সহায়তা প্রয়োজন এমন মানুষের সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'প্রয়োজনীয় উপকরণ',
    needLabels: {
      water: 'পানি', food: 'খাবার', clothing: 'পোশাক', sanitation: 'স্যানিটেশন', power: 'বিদ্যুৎ', fuel: 'জ্বালানি',
    },
  },
  SHELTER_INFO: {
    label: 'আশ্রয়কেন্দ্রের তথ্য',
    shortLabel: 'আশ্রয়',
    helper: 'আশ্রয়কেন্দ্রের খালি জায়গা, ধারণক্ষমতা বা অনুপস্থিত সেবার তথ্য দিন।',
    descriptionLabel: 'আশ্রয়কেন্দ্রের বর্তমান অবস্থা কী?',
    descriptionPlaceholder: 'খালি জায়গা, ধারণক্ষমতা, প্রবেশপথ ও বর্তমান অবস্থার বিবরণ লিখুন',
    peopleCountLabel: 'আশ্রিত বা অপেক্ষমাণ মানুষের সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'আশ্রয়কেন্দ্রে প্রয়োজনীয় সেবা',
    needLabels: {
      water: 'পানি', food: 'খাবার', medical: 'চিকিৎসা', sanitation: 'স্যানিটেশন', accessibility: 'প্রতিবন্ধীবান্ধব প্রবেশপথ',
    },
  },
  HAZARD_UPDATE: {
    label: 'বিপদের হালনাগাদ',
    shortLabel: 'বিপদ',
    helper: 'বন্যা, আগুন, ধস, দূষণ বা সড়কের পরিবর্তিত বিপদের তথ্য দিন।',
    descriptionLabel: 'কী বিপদ দেখেছেন?',
    descriptionPlaceholder: 'বিপদ, ছড়ানোর দিক এবং কাছাকাছি পরিচিত স্থানের বিবরণ লিখুন',
    peopleCountLabel: 'ঝুঁকিতে থাকা মানুষের সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'যে প্রতিক্রিয়া প্রয়োজন',
    needLabels: {
      evacuation: 'নিরাপদ স্থানে সরানো', rescue: 'উদ্ধার', road_clearance: 'রাস্তা পরিষ্কার', fire_service: 'ফায়ার সার্ভিস', medical: 'চিকিৎসা',
    },
  },
  SAFETY_STATUS: {
    label: 'নিরাপত্তার অবস্থা',
    shortLabel: 'নিরাপত্তা',
    helper: 'মানুষ নিরাপদ, আহত, আটকা বা স্থানান্তরের প্রয়োজন—তা জানান।',
    descriptionLabel: 'বর্তমান নিরাপত্তার অবস্থা কী?',
    descriptionPlaceholder: 'অপ্রয়োজনীয় পরিচয় না দিয়ে কারা নিরাপদ বা ঝুঁকিতে আছেন তা লিখুন',
    peopleCountLabel: 'এই হালনাগাদের অন্তর্ভুক্ত মানুষের সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'এখনো যে সহায়তা প্রয়োজন',
    needLabels: {
      medical: 'চিকিৎসা', evacuation: 'নিরাপদ স্থানে সরানো', rescue: 'উদ্ধার', contact_family: 'পরিবারের সঙ্গে যোগাযোগ',
    },
  },
  SAFE_ROUTE: {
    label: 'নিরাপদ পথ',
    shortLabel: 'নিরাপদ পথ',
    helper: 'চলাচলযোগ্য নিরাপদ পথ বা পথটিতে প্রয়োজনীয় সহায়তার তথ্য দিন।',
    descriptionLabel: 'পথটি কোথায় যায় এবং কেন নিরাপদ?',
    descriptionPlaceholder: 'শুরুর স্থান, গন্তব্য, পরিচিত স্থান, বাধা ও চলার দিক লিখুন',
    peopleCountLabel: 'সম্ভাব্য ব্যবহারকারীর সংখ্যা (ঐচ্ছিক)',
    needsLabel: 'পথে যে সহায়তা প্রয়োজন',
    needLabels: {
      transport: 'পরিবহন', road_clearance: 'রাস্তা পরিষ্কার', signage: 'দিকনির্দেশনা চিহ্ন', escort: 'নিরাপত্তা সহায়তা', medical: 'চিকিৎসা',
    },
  },
};

const CONFIG_BY_TYPE = new Map(REPORT_FORM_CONFIGS.map(config => [config.type, config]));

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  SOS: 'Emergency SOS',
  MEDICAL_NEED: 'Medical need',
  RESOURCE_NEED: 'Resource need',
  SAFETY_STATUS: 'Safety status',
  SHELTER_INFO: 'Shelter information',
  HAZARD_UPDATE: 'Hazard update',
  SAFE_ROUTE: 'Safe route',
  INSTRUCTION: 'Responder instruction',
};

const BANGLA_REPORT_TYPE_LABELS: Record<ReportType, string> = {
  SOS: 'জরুরি এসওএস',
  MEDICAL_NEED: 'চিকিৎসা সহায়তা',
  RESOURCE_NEED: 'জরুরি উপকরণের প্রয়োজন',
  SAFETY_STATUS: 'নিরাপত্তার অবস্থা',
  SHELTER_INFO: 'আশ্রয়কেন্দ্রের তথ্য',
  HAZARD_UPDATE: 'বিপদের হালনাগাদ',
  SAFE_ROUTE: 'নিরাপদ পথ',
  INSTRUCTION: 'উদ্ধারকর্মীর নির্দেশনা',
};

export function getReportFormConfigs(language: AppLanguage = 'en'): readonly ReportFormConfig[] {
  if (language === 'en') return REPORT_FORM_CONFIGS;
  return REPORT_FORM_CONFIGS.map(config => {
    const copy = BANGLA_FORM_COPY[config.type];
    return {
      ...config,
      ...copy,
      needs: config.needs.map(need => ({
        value: need.value,
        label: copy.needLabels[need.value] ?? need.label,
      })),
    };
  });
}

export function getReportTypeLabel(type: ReportType, language: AppLanguage = 'en'): string {
  return language === 'bn' ? BANGLA_REPORT_TYPE_LABELS[type] : REPORT_TYPE_LABELS[type];
}

export function getReportFormConfig(
  type: CreatableReportType,
  language: AppLanguage = 'en',
): ReportFormConfig {
  const config = CONFIG_BY_TYPE.get(type);
  if (!config) throw new Error(`No report form configuration exists for ${type}.`);
  if (language === 'en') return config;
  const copy = BANGLA_FORM_COPY[type];
  return {
    ...config,
    ...copy,
    needs: config.needs.map(need => ({
      value: need.value,
      label: copy.needLabels[need.value] ?? need.label,
    })),
  };
}
