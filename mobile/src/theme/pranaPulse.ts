import { TextStyle, ViewStyle } from 'react-native';

export const pranaPulseTheme = {
  fonts: {
    regular: 'PlusJakartaSans_400Regular',
    medium: 'PlusJakartaSans_500Medium',
    semiBold: 'PlusJakartaSans_600SemiBold',
    bold: 'PlusJakartaSans_700Bold',
    extraBold: 'PlusJakartaSans_800ExtraBold',
  },
  colors: {
    background: '#FEFFD6',
    surface: '#FEFFD6',
    surfaceDim: '#E5E3D4',
    surfaceContainerLow: '#FCF9EE',
    surfaceContainer: '#F6F4E7',
    surfaceContainerHigh: '#F0EEE1',
    surfaceContainerHighest: '#EBE9D9',
    surfaceContainerLowest: '#FFFFFF',
    primary: '#556A48',
    primaryDim: '#4A5E3D',
    primaryContainer: '#D2EABF',
    secondary: '#8C573A',
    secondaryContainer: '#FFDBCA',
    tertiary: '#845C32',
    tertiaryContainer: '#D9A777',
    onBackground: '#38382E',
    onSurface: '#38382E',
    onSurfaceVariant: '#656559',
    onPrimary: '#FFFFFF',
    outline: '#828174',
    outlineVariant: '#BBBAAB',
    error: '#AE4025',
    errorContainer: '#FD795A',
    white: '#FFFFFF',
  },
  spacing: {
    xs: 8,
    sm: 12,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 40,
  },
  radius: {
    sm: 16,
    md: 24,
    lg: 32,
    xl: 48,
    full: 9999,
  },
  type: {
    eyebrow: {
      fontFamily: 'PlusJakartaSans_700Bold',
      color: '#656559',
      fontSize: 12,
      letterSpacing: 1.2,
      textTransform: 'uppercase',
    } satisfies TextStyle,
    body: {
      fontFamily: 'PlusJakartaSans_500Medium',
      color: '#656559',
      fontSize: 15,
      lineHeight: 24,
    } satisfies TextStyle,
    display: {
      fontFamily: 'PlusJakartaSans_800ExtraBold',
      color: '#38382E',
      fontSize: 34,
      letterSpacing: -0.8,
    } satisfies TextStyle,
    title: {
      fontFamily: 'PlusJakartaSans_800ExtraBold',
      color: '#38382E',
      fontSize: 20,
      letterSpacing: -0.4,
    } satisfies TextStyle,
    label: {
      fontFamily: 'PlusJakartaSans_700Bold',
      color: '#656559',
      fontSize: 13,
    } satisfies TextStyle,
  },
} as const;

export const pranaPulseShadow: ViewStyle = {
  shadowColor: '#38382E',
  shadowOffset: { width: 0, height: 10 },
  shadowOpacity: 0.08,
  shadowRadius: 24,
  elevation: 6,
};

export function withAlpha(hex: string, alpha: number): string {
  const safeAlpha = Math.max(0, Math.min(1, alpha));
  const opacity = Math.round(safeAlpha * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${opacity}`;
}
