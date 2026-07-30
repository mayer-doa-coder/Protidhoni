import type {ReportType} from '../contracts/report';

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

export function getReportFormConfig(type: CreatableReportType): ReportFormConfig {
  const config = CONFIG_BY_TYPE.get(type);
  if (!config) throw new Error(`No report form configuration exists for ${type}.`);
  return config;
}
