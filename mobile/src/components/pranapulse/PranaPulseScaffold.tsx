import { MaterialIcons } from '@expo/vector-icons';
import React, { ReactNode, useContext } from 'react';
import {
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  TouchableOpacity,
  useWindowDimensions,
  View,
  ViewStyle,
} from 'react-native';
import { SafeAreaInsetsContext, SafeAreaView } from 'react-native-safe-area-context';
import { pranaPulseTheme, withAlpha } from '../../theme/pranaPulse';
import { PranaPulseBottomNav, PranaPulseTab } from './PranaPulseBottomNav';

interface PranaPulseScaffoldProps {
  activeTab: PranaPulseTab;
  children: ReactNode;
  profileLabel?: string;
  showBottomNav?: boolean;
  showHeader?: boolean;
  scroll?: boolean;
  contentContainerStyle?: StyleProp<ViewStyle>;
  onHomePress?: () => void;
  onCirclePress?: () => void;
  onScanPress?: () => void;
  onResultsPress?: () => void;
}

export function PranaPulseScaffold({
  activeTab,
  children,
  profileLabel,
  showBottomNav = true,
  showHeader = true,
  scroll = true,
  contentContainerStyle,
  onHomePress,
  onCirclePress,
  onScanPress,
  onResultsPress,
}: PranaPulseScaffoldProps) {
  const insets = useContext(SafeAreaInsetsContext) ?? { top: 0, right: 0, bottom: 0, left: 0 };
  const { width: screenWidth } = useWindowDimensions();
  const isCompact = screenWidth < 390;
  const bottomOffset = Math.max(insets.bottom, 12);
  const contentBottomPadding = (showBottomNav ? 128 : 40) + bottomOffset;
  const avatarLetter = (profileLabel ?? 'P').trim().charAt(0).toUpperCase() || 'P';
  const shellHorizontalPadding = isCompact ? 18 : 20;
  const contentHorizontalPadding = isCompact ? 18 : 24;
  const contentMaxWidth = Math.min(screenWidth, 440);

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.safeArea}>
      <View style={styles.container}>
        <View pointerEvents="none" style={styles.backgroundLayer}>
          <View style={styles.primaryBlob} />
          <View style={styles.secondaryBlob} />
        </View>

        {showHeader ? (
          <View style={[styles.header, { paddingHorizontal: shellHorizontalPadding }]}>
            <View style={[styles.headerInner, { maxWidth: contentMaxWidth }]}>
              <View style={styles.brandRow}>
                <View style={styles.avatarShell}>
                  <View style={styles.avatarCore}>
                    <Text style={styles.avatarText}>{avatarLetter}</Text>
                  </View>
                </View>
                <Text style={styles.brandText}>PranaPulse</Text>
              </View>

              <TouchableOpacity accessibilityRole="button" style={styles.settingsButton}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="settings" size={20} />
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        {scroll ? (
          <ScrollView
            contentInsetAdjustmentBehavior="automatic"
            contentContainerStyle={[
              styles.contentContainer,
              { maxWidth: contentMaxWidth, paddingHorizontal: contentHorizontalPadding },
              { paddingBottom: contentBottomPadding },
              contentContainerStyle,
            ]}
            keyboardDismissMode="on-drag"
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            {children}
          </ScrollView>
        ) : (
          <View
            style={[
              styles.contentContainer,
              styles.fillContent,
              { maxWidth: contentMaxWidth, paddingHorizontal: contentHorizontalPadding },
              { paddingBottom: contentBottomPadding },
              contentContainerStyle,
            ]}
          >
            {children}
          </View>
        )}

        {showBottomNav ? (
          <View
            style={[
              styles.bottomNavWrapper,
              {
                bottom: bottomOffset,
                left: shellHorizontalPadding,
                right: shellHorizontalPadding,
                maxWidth: contentMaxWidth,
              },
            ]}
          >
            <PranaPulseBottomNav
              activeTab={activeTab}
              onCirclePress={onCirclePress}
              onHomePress={onHomePress}
              onResultsPress={onResultsPress}
              onScanPress={onScanPress}
            />
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: pranaPulseTheme.colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: pranaPulseTheme.colors.background,
  },
  backgroundLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  primaryBlob: {
    position: 'absolute',
    top: 72,
    left: -56,
    width: 244,
    height: 244,
    borderRadius: 999,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.44),
  },
  secondaryBlob: {
    position: 'absolute',
    right: -76,
    bottom: 118,
    width: 288,
    height: 288,
    borderRadius: 999,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.42),
  },
  header: {
    paddingTop: 8,
    paddingBottom: 10,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surface, 0.74),
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.3),
  },
  headerInner: {
    width: '100%',
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  avatarShell: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.92),
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.9),
  },
  avatarCore: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.9),
  },
  avatarText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 14,
  },
  brandText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 20,
    letterSpacing: -0.4,
  },
  settingsButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.72),
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.34),
  },
  contentContainer: {
    width: '100%',
    alignSelf: 'center',
    paddingTop: 18,
  },
  fillContent: {
    flex: 1,
  },
  bottomNavWrapper: {
    position: 'absolute',
    alignSelf: 'center',
  },
});
