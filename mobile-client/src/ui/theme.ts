/**
 * Shared design tokens, sourced from the "Tranzparency" SOS Emergency app UI
 * Kit style guide (Figma, color-palette frame `1:557`): #FF8852 / #313A51 /
 * #8B8B8B / #F5F5FA / #FFFFFF. Every screen should read colors/spacing from
 * here instead of hand-picking new hex values, so the app reads as one
 * consistent product instead of five differently-styled screens.
 */

export const colors = {
  /** Primary brand/action color (SOS button, active tab, primary CTA). */
  primary: '#FF8852',
  primaryDark: '#E85A2A',
  /** Deep navy used for all body text/headings on light surfaces. */
  ink: '#313A51',
  inkMuted: '#6B7280',
  /** Neutral grey for secondary/disabled content. */
  neutral: '#8B8B8B',
  /** App background. */
  background: '#F5F5FA',
  surface: '#FFFFFF',
  surfaceBorder: '#EFEFEF',
  /** Status colors, kept distinct from the brand palette on purpose. */
  danger: '#DC2626',
  success: '#16A34A',
  warning: '#CA8A04',
  info: '#2563EB',
  overlay: 'rgba(49, 58, 81, 0.55)',
} as const;

/** Soft category tones behind the Home screen's emergency-type chips —
 * matches the Figma reference's pastel icon badges (mint/lilac/rose/olive). */
export const categoryTint = {
  MEDICAL_NEED: '#A6F5D4',
  RESOURCE_NEED: '#F5E8A6',
  SHELTER_INFO: '#D4CEFA',
  HAZARD_UPDATE: '#FFD1B8',
  SAFETY_STATUS: '#F5A6DF',
  SAFE_ROUTE: '#DBE790',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 10,
  md: 16,
  lg: 20,
  pill: 999,
} as const;

export const shadow = {
  card: {
    shadowColor: '#313A51',
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: {width: 0, height: 4},
    elevation: 3,
  },
} as const;
