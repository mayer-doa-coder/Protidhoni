import {describe, expect, it} from 'vitest';

import type {CrisisReport, ReportPriority} from './api';
import {hasMappableLocation, priorityLabel, reportPinColour} from './reportPresentation';

describe('report presentation', () => {
  it('assigns a distinct colour to every priority including unscored', () => {
    const priorities: ReportPriority[] = ['critical', 'high', 'medium', 'low', null];
    const colours = priorities.map(reportPinColour);
    expect(new Set(colours).size).toBe(5);
    expect(priorityLabel(null)).toBe('unscored');
  });

  it('only maps reports with both finite coordinates', () => {
    const report = {location: {lat: 23.8, lng: 90.4}} as CrisisReport;
    expect(hasMappableLocation(report)).toBe(true);

    report.location.lng = null;
    expect(hasMappableLocation(report)).toBe(false);
  });
});
