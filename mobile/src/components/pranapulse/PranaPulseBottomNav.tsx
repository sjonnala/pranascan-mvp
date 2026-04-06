import { MaterialCommunityIcons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../../theme/pranaPulse';

export type PranaPulseTab = 'home' | 'circle' | 'scan' | 'results';

type NavAction = (() => void) | undefined;

interface NavItemProps {
  active: boolean;
  icon: React.ComponentProps<typeof MaterialCommunityIcons>['name'];
  label: string;
  onPress?: NavAction;
}

function NavItem({ active, icon, label, onPress }: NavItemProps) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      disabled={!onPress}
      onPress={onPress}
      style={({ pressed }) => [
        styles.navItem,
        pressed && onPress ? styles.navItemPressed : null,
      ]}
    >
      {active ? <View pointerEvents="none" style={styles.activeHalo} /> : null}
      <View style={[styles.iconShell, active ? styles.iconShellActive : null]}>
        <MaterialCommunityIcons
          color={active ? pranaPulseTheme.colors.onPrimary : pranaPulseTheme.colors.onSurfaceVariant}
          name={icon}
          size={22}
        />
      </View>
    </Pressable>
  );
}

interface PranaPulseBottomNavProps {
  activeTab: PranaPulseTab;
  onHomePress?: NavAction;
  onCirclePress?: NavAction;
  onScanPress?: NavAction;
  onResultsPress?: NavAction;
}

export function PranaPulseBottomNav({
  activeTab,
  onHomePress,
  onCirclePress,
  onScanPress,
  onResultsPress,
}: PranaPulseBottomNavProps) {
  return (
    <View style={styles.navShell}>
      <NavItem active={activeTab === 'home'} icon="home-heart" label="Home" onPress={onHomePress} />
      <NavItem active={activeTab === 'circle'} icon="account-group" label="Circle" onPress={onCirclePress} />
      <NavItem active={activeTab === 'scan'} icon="square-edit-outline" label="Scan" onPress={onScanPress} />
      <NavItem active={activeTab === 'results'} icon="chart-box-outline" label="Trend" onPress={onResultsPress} />
    </View>
  );
}

const styles = StyleSheet.create({
  navShell: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 36,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surface, 0.86),
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.34),
    ...pranaPulseShadow,
  },
  navItem: {
    position: 'relative',
    minWidth: 56,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
  navItemPressed: {
    opacity: 0.82,
  },
  activeHalo: {
    position: 'absolute',
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.42),
  },
  iconShell: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconShellActive: {
    backgroundColor: pranaPulseTheme.colors.primary,
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.68),
  },
});
