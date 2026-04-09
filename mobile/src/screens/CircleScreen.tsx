import { MaterialIcons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { getCurrentVitalityStreak, getScanHistory, listSocialConnections } from '../api/client';
import { PranaPulseReveal } from '../components/pranapulse/PranaPulseReveal';
import { PranaPulseScaffold } from '../components/pranapulse/PranaPulseScaffold';
import { ScanHistoryPage, SocialConnection, VitalityStreak } from '../types';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';

interface CircleScreenProps {
  currentUserId: string;
  displayName?: string | null;
  onOpenHome: () => void;
  onOpenScan: () => void;
  onOpenResults: () => void;
}

interface CircleMember {
  id: string;
  name: string;
  glow: 'sage' | 'sunset';
}

interface StreakCard {
  id: string;
  icon: React.ComponentProps<typeof MaterialIcons>['name'];
  name: string;
  tone: 'sage' | 'sunset';
  value: string;
}

function getPartnerName(connection: SocialConnection, currentUserId: string): string {
  return connection.requesterUserId === currentUserId
    ? connection.addresseeDisplayName
    : connection.requesterDisplayName;
}

function glowFromIndex(index: number): CircleMember['glow'] {
  return index % 2 === 0 ? 'sage' : 'sunset';
}

function formatShortDate(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

export function CircleScreen({
  currentUserId,
  displayName,
  onOpenHome,
  onOpenResults,
  onOpenScan,
}: CircleScreenProps) {
  const [connections, setConnections] = useState<SocialConnection[]>([]);
  const [streak, setStreak] = useState<VitalityStreak | null>(null);
  const [history, setHistory] = useState<ScanHistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    (async () => {
      const [connectionsResult, streakResult, historyResult] = await Promise.allSettled([
        listSocialConnections(),
        getCurrentVitalityStreak(),
        getScanHistory(1, 3),
      ]);

      if (!isMounted) {
        return;
      }

      if (connectionsResult.status === 'fulfilled') {
        setConnections(connectionsResult.value);
      }
      if (streakResult.status === 'fulfilled') {
        setStreak(streakResult.value);
      }
      if (historyResult.status === 'fulfilled') {
        setHistory(historyResult.value);
      }

      if (
        connectionsResult.status === 'rejected' ||
        streakResult.status === 'rejected' ||
        historyResult.status === 'rejected'
      ) {
        setError('Some circle details are still loading. Live connection and streak data may be partial.');
      }

      setIsLoading(false);
    })().catch(() => {
      if (isMounted) {
        setError('Some circle details are still loading. Live connection and streak data may be partial.');
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  const acceptedConnections = useMemo(
    () => connections.filter((connection) => connection.status === 'ACCEPTED'),
    [connections]
  );

  const members = useMemo(() => {
    return acceptedConnections
      .map((connection, index) => ({
        id: connection.id,
        name: getPartnerName(connection, currentUserId),
        glow: glowFromIndex(index),
      }))
      .slice(0, 4);
  }, [acceptedConnections, currentUserId]);

  const currentUserName = displayName?.trim() || 'You';
  const latestConnection = useMemo(() => {
    return [...connections].sort((left, right) => {
      const leftTime = new Date(left.respondedAt ?? left.createdAt).getTime();
      const rightTime = new Date(right.respondedAt ?? right.createdAt).getTime();
      return rightTime - leftTime;
    })[0] ?? null;
  }, [connections]);
  const latestConnectionName = latestConnection
    ? getPartnerName(latestConnection, currentUserId)
    : null;
  const acceptedCount = acceptedConnections.length;
  const pendingCount = connections.filter((connection) => connection.status === 'PENDING').length;
  const latestScan = history?.items[0] ?? null;
  const streakValue = streak?.currentStreakDays != null ? `${streak.currentStreakDays} Days Active` : 'Ready to begin';
  const streakHeadline =
    streak?.currentStreakDays != null
      ? `${currentUserName} has maintained a calmness streak for ${streak.currentStreakDays} days`
      : 'Complete your next Daily Glow check-in to start a shared rhythm.';
  const filledDots = Math.max(
    1,
    Math.min(5, Math.ceil((streak?.currentStreakDays ?? (latestScan ? 1 : 0)) / 3))
  );
  const connectionHeadline = latestConnectionName
    ? latestConnection.status === 'ACCEPTED'
      ? `${latestConnectionName} is now part of your circle`
      : `Invite pending with ${latestConnectionName}`
    : 'Invite someone to start your first shared check-in.';
  const connectionMetric = latestConnection
    ? `${latestConnection.status === 'ACCEPTED' ? 'Connected' : 'Requested'} • ${formatShortDate(latestConnection.respondedAt ?? latestConnection.createdAt) ?? 'Today'}`
    : `${acceptedCount} connections live`;

  const streakCards = useMemo<StreakCard[]>(() => {
    const cards: StreakCard[] = [
      { id: 'self', icon: 'auto-awesome', name: currentUserName, tone: 'sage', value: streakValue },
    ];

    connections.slice(0, 3).forEach((connection, index) => {
      cards.push({
        id: `member-${connection.id}`,
        icon: connection.status === 'ACCEPTED' ? 'self-improvement' : 'schedule',
        name: getPartnerName(connection, currentUserId),
        tone: index % 2 === 0 ? 'sage' : 'sunset',
        value:
          connection.status === 'ACCEPTED'
            ? `Connected ${formatShortDate(connection.respondedAt ?? connection.createdAt) ?? 'recently'}`
            : `Invited ${formatShortDate(connection.createdAt) ?? 'recently'}`,
      });
    });

    return cards;
  }, [connections, currentUserId, currentUserName, streakValue]);

  return (
    <PranaPulseScaffold
      activeTab="circle"
      onCirclePress={() => undefined}
      onHomePress={onOpenHome}
      onResultsPress={onOpenResults}
      onScanPress={onOpenScan}
      profileLabel={displayName ?? 'P'}
    >
      <PranaPulseReveal delay={10}>
        <View style={styles.heroSection}>
          <Text style={styles.eyebrow}>Vitality Glow</Text>
          <Text style={styles.heroTitle}>Collective Breath</Text>
          <Text style={styles.heroSubtitle}>
            Sharing stillness with those around you. A community of consistent calm.
          </Text>
        </View>
      </PranaPulseReveal>

      <PranaPulseReveal delay={90}>
        <View style={styles.circleSection}>
          <View style={styles.sectionRow}>
            <Text style={styles.sectionTitle}>My Circle</Text>
            {isLoading ? <ActivityIndicator color={pranaPulseTheme.colors.primary} /> : null}
          </View>

          <ScrollView
            contentContainerStyle={styles.avatarScroller}
            horizontal
            showsHorizontalScrollIndicator={false}
          >
            {members.map((member) => (
              <View key={member.id} style={styles.avatarGroup}>
                <View
                  style={[
                    styles.avatarHalo,
                    member.glow === 'sage' ? styles.sageHalo : styles.sunsetHalo,
                  ]}
                >
                  <View style={styles.avatarCore}>
                    <Text style={styles.avatarInitial}>{member.name.charAt(0).toUpperCase()}</Text>
                  </View>
                </View>
                <Text style={styles.avatarName}>{member.name}</Text>
              </View>
            ))}

            <TouchableOpacity onPress={onOpenScan} style={styles.avatarGroup}>
              <View style={styles.addAvatar}>
                <MaterialIcons color={pranaPulseTheme.colors.onSurfaceVariant} name="add" size={28} />
              </View>
              <Text style={styles.avatarMuted}>Add</Text>
            </TouchableOpacity>
          </ScrollView>

          {!isLoading && members.length === 0 ? (
            <Text style={styles.emptyStateCopy}>
              No one is in your circle yet. Invite someone after your next Daily Glow check-in.
            </Text>
          ) : null}
        </View>
      </PranaPulseReveal>

      {error ? <Text style={styles.inlineError}>{error}</Text> : null}

      <PranaPulseReveal delay={180}>
        <View style={styles.streakSection}>
          <Text style={styles.sectionTitleMuted}>Presence Streaks</Text>
          <View style={styles.streakGrid}>
            {streakCards.map((card) => (
              <View key={card.id} style={styles.streakCard}>
                <View
                  style={[
                    styles.streakIconShell,
                    card.tone === 'sage' ? styles.streakIconSage : styles.streakIconSunset,
                  ]}
                >
                  <MaterialIcons
                    color={
                      card.tone === 'sage'
                        ? pranaPulseTheme.colors.primary
                        : pranaPulseTheme.colors.secondary
                    }
                    name={card.icon}
                    size={24}
                  />
                </View>
                <View style={styles.streakTextGroup}>
                  <Text style={styles.streakName}>{card.name}</Text>
                  <Text
                    style={[
                      styles.streakValue,
                      card.tone === 'sage' ? styles.primaryText : styles.secondaryText,
                    ]}
                  >
                    {card.value}
                  </Text>
                </View>
              </View>
            ))}

            <View style={styles.interactionCard}>
              <MaterialIcons color={pranaPulseTheme.colors.tertiary} name="celebration" size={26} />
              <Text style={styles.interactionTitle}>Send a 'Nudge' of Love</Text>
              <TouchableOpacity onPress={onOpenResults}>
                <Text style={styles.interactionLink}>
                  {pendingCount > 0
                    ? `${pendingCount} pending invite${pendingCount > 1 ? 's' : ''}`
                    : acceptedCount > 0
                      ? `${acceptedCount} active connection${acceptedCount > 1 ? 's' : ''}`
                      : 'Start your circle'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </PranaPulseReveal>

      <PranaPulseReveal delay={260}>
        <View style={styles.feedSection}>
          <Text style={styles.sectionTitle}>Vitality Glow Feed</Text>

          <Pressable style={({ pressed }) => [styles.feedCard, pressed && styles.pressed]}>
            <View style={styles.feedHeader}>
              <View style={[styles.feedAvatarHalo, styles.sageHalo]}>
                <View style={styles.feedAvatarCore}>
                  <Text style={styles.feedAvatarText}>{currentUserName.charAt(0).toUpperCase()}</Text>
                </View>
              </View>
              <View style={styles.feedIdentity}>
                <Text style={styles.feedName}>{currentUserName}</Text>
                <Text style={styles.feedMeta}>
                  {formatShortDate(streak?.lastCheckInOn ?? latestScan?.session.completed_at ?? latestScan?.session.created_at) ?? 'Today'}
                </Text>
              </View>
            </View>

            <View style={styles.feedHighlight}>
              <View style={styles.feedHighlightIcon}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="auto-awesome" size={28} />
              </View>
              <Text style={styles.feedHighlightTitle}>{streakHeadline}</Text>
              <View style={styles.dotRow}>
                {Array.from({ length: 5 }, (_, index) =>
                  index < filledDots ? (
                    <View key={`filled-${index}`} style={styles.dotFilled} />
                  ) : (
                    <View key={`muted-${index}`} style={styles.dotMuted} />
                  )
                )}
              </View>
            </View>

            <View style={styles.feedFooter}>
              <View style={styles.smallAvatarStack}>
                {members.slice(0, 2).map((member) => (
                  <View
                    key={`stack-${member.id}`}
                    style={[
                      styles.smallAvatar,
                      member.glow === 'sage' ? styles.sageHalo : styles.sunsetHalo,
                    ]}
                  />
                ))}
              </View>
              <Text style={styles.feedAction}>Acknowledge</Text>
            </View>
          </Pressable>

          <View style={styles.feedCard}>
            <View style={styles.feedHeader}>
              <View style={[styles.feedAvatarHalo, styles.sunsetHalo]}>
                <View style={styles.feedAvatarCore}>
                  <Text style={styles.feedAvatarText}>{latestConnectionName?.charAt(0).toUpperCase() ?? 'C'}</Text>
                </View>
              </View>
              <View style={styles.feedIdentity}>
                <Text style={styles.feedName}>{latestConnectionName ?? 'Circle'}</Text>
                <Text style={styles.feedMeta}>
                  {formatShortDate(latestConnection?.respondedAt ?? latestConnection?.createdAt) ?? 'Waiting for activity'}
                </Text>
              </View>
            </View>

            <Text style={styles.feedHeadline}>{connectionHeadline}</Text>

            <View style={styles.feedMediaCard}>
              <View style={styles.feedMediaBackdrop} />
              <View style={styles.feedMediaOverlay} />
              <View style={styles.feedMediaMetricRow}>
                <MaterialIcons
                  color={pranaPulseTheme.colors.white}
                  name={latestConnection?.status === 'ACCEPTED' ? 'favorite' : 'schedule'}
                  size={14}
                />
                <Text style={styles.feedMediaMetric}>{connectionMetric}</Text>
              </View>
            </View>

            <View style={styles.feedActionsRow}>
              <Text style={styles.feedAction}>{acceptedCount > 0 ? 'Celebrate' : 'Invite'}</Text>
              <Text style={styles.feedAction}>{pendingCount > 0 ? 'Follow Up' : 'Reflect'}</Text>
            </View>
          </View>

          <View style={styles.communityCard}>
            <View style={styles.communityHeader}>
              <View>
                <Text style={styles.communityTitle}>Community Pulse</Text>
                <Text style={styles.communityCopy}>
                  {acceptedCount > 0
                    ? `${acceptedCount} active connection${acceptedCount > 1 ? 's' : ''} · ${history?.total ?? 0} scans logged in your timeline.`
                    : 'Invite one trusted person to begin a shared calm rhythm.'}
                </Text>
              </View>
              <MaterialIcons color={pranaPulseTheme.colors.white} name="waves" size={28} />
            </View>

            <View style={styles.pulseBars}>
              <View style={[styles.pulseBar, styles.pulseBarLow]} />
              <View style={[styles.pulseBar, styles.pulseBarMedium]} />
              <View style={[styles.pulseBar, styles.pulseBarHigh]} />
              <View style={[styles.pulseBar, styles.pulseBarMedium]} />
              <View style={[styles.pulseBar, styles.pulseBarLow]} />
            </View>

            <Text style={styles.communityFooter}>
              {formatShortDate(latestScan?.session.completed_at ?? latestScan?.session.created_at)
                ? `Latest check-in ${formatShortDate(latestScan?.session.completed_at ?? latestScan?.session.created_at)}`
                : 'Your next Daily Glow will appear here'}
            </Text>
          </View>
        </View>
      </PranaPulseReveal>
    </PranaPulseScaffold>
  );
}

const styles = StyleSheet.create({
  heroSection: {
    marginBottom: 24,
    gap: 6,
  },
  eyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.primary,
  },
  heroTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 32,
    letterSpacing: -0.7,
  },
  heroSubtitle: {
    ...pranaPulseTheme.type.body,
    maxWidth: 330,
  },
  circleSection: {
    marginBottom: 18,
  },
  sectionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  sectionTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 20,
  },
  avatarScroller: {
    gap: 18,
    paddingVertical: 10,
    paddingHorizontal: 2,
  },
  avatarGroup: {
    alignItems: 'center',
    gap: 10,
  },
  avatarHalo: {
    width: 82,
    height: 82,
    borderRadius: 41,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 4,
  },
  sageHalo: {
    backgroundColor: pranaPulseTheme.colors.primaryContainer,
  },
  sunsetHalo: {
    backgroundColor: pranaPulseTheme.colors.secondaryContainer,
  },
  avatarCore: {
    width: '100%',
    height: '100%',
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: pranaPulseTheme.colors.surface,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.92),
  },
  avatarInitial: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 22,
  },
  avatarName: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 13,
  },
  addAvatar: {
    width: 82,
    height: 82,
    borderRadius: 41,
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: pranaPulseTheme.colors.outlineVariant,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarMuted: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
  },
  emptyStateCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
    marginTop: 8,
  },
  inlineError: {
    color: pranaPulseTheme.colors.error,
    fontSize: 13,
    lineHeight: 20,
    marginBottom: 18,
  },
  streakSection: {
    marginBottom: 22,
  },
  sectionTitleMuted: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 18,
    marginBottom: 12,
  },
  streakGrid: {
    flexDirection: 'column',
    gap: 10,
  },
  streakCard: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    ...pranaPulseShadow,
  },
  streakIconShell: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  streakIconSage: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.76),
  },
  streakIconSunset: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.84),
  },
  streakTextGroup: {
    flex: 1,
    gap: 3,
  },
  streakName: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  streakValue: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    fontSize: 17,
    lineHeight: 22,
  },
  primaryText: {
    color: pranaPulseTheme.colors.primary,
  },
  secondaryText: {
    color: pranaPulseTheme.colors.secondary,
  },
  interactionCard: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: withAlpha(pranaPulseTheme.colors.tertiaryContainer, 0.46),
    padding: 20,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    marginTop: 4,
  },
  interactionTitle: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
    textAlign: 'center',
  },
  interactionLink: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  feedSection: {
    gap: 14,
  },
  feedCard: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    padding: 20,
    gap: 16,
    ...pranaPulseShadow,
  },
  feedHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  feedAvatarHalo: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 3,
  },
  feedAvatarCore: {
    width: '100%',
    height: '100%',
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.92),
  },
  feedAvatarText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 18,
  },
  feedIdentity: {
    gap: 2,
  },
  feedName: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 15,
  },
  feedMeta: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 12,
  },
  feedHighlight: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLow,
    padding: 24,
    alignItems: 'center',
    gap: 14,
  },
  feedHighlightIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.32),
  },
  feedHighlightTitle: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 21,
    lineHeight: 29,
    textAlign: 'center',
  },
  dotRow: {
    flexDirection: 'row',
    gap: 6,
  },
  dotFilled: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  dotMuted: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primary, 0.26),
  },
  feedFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  smallAvatarStack: {
    flexDirection: 'row',
    marginLeft: 4,
  },
  smallAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    marginLeft: -8,
    borderWidth: 2,
    borderColor: pranaPulseTheme.colors.surfaceContainerLowest,
  },
  feedAction: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 14,
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 20,
    paddingVertical: 8,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.52),
    overflow: 'hidden',
  },
  feedHeadline: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 18,
    lineHeight: 26,
  },
  feedMediaCard: {
    overflow: 'hidden',
    borderRadius: pranaPulseTheme.radius.md,
    height: 190,
    justifyContent: 'flex-end',
    padding: 16,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondary, 0.12),
  },
  feedMediaBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondary, 0.18),
  },
  feedMediaOverlay: {
    position: 'absolute',
    left: -30,
    right: -30,
    bottom: -24,
    height: 180,
    borderRadius: 120,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.72),
  },
  feedMediaMetricRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  feedMediaMetric: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.white,
    fontSize: 13,
  },
  feedActionsRow: {
    flexDirection: 'row',
    gap: 24,
  },
  communityCard: {
    borderRadius: pranaPulseTheme.radius.lg,
    backgroundColor: pranaPulseTheme.colors.primary,
    padding: 22,
    gap: 10,
    marginBottom: 8,
  },
  communityHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  communityTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 22,
  },
  communityCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: withAlpha(pranaPulseTheme.colors.white, 0.84),
    fontSize: 14,
    lineHeight: 22,
    maxWidth: 210,
  },
  pulseBars: {
    height: 94,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    marginTop: 8,
    marginBottom: 4,
  },
  pulseBar: {
    flex: 1,
    borderTopLeftRadius: 999,
    borderTopRightRadius: 999,
  },
  pulseBarLow: {
    height: '36%',
    backgroundColor: withAlpha(pranaPulseTheme.colors.white, 0.24),
  },
  pulseBarMedium: {
    height: '66%',
    backgroundColor: withAlpha(pranaPulseTheme.colors.white, 0.42),
  },
  pulseBarHigh: {
    height: '90%',
    backgroundColor: withAlpha(pranaPulseTheme.colors.white, 0.62),
  },
  communityFooter: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: withAlpha(pranaPulseTheme.colors.white, 0.76),
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
    textAlign: 'center',
  },
  pressed: {
    opacity: 0.94,
  },
});
