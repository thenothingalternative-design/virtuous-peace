/**
 * HomeScreen
 *
 * Main screen. Matches the desktop layout closely:
 * - Session goal input
 * - Active profile badge
 * - Allowed apps chips
 * - Blocked keywords chips
 * - Start / Stop session button
 * - Live elapsed time + blocked count
 * - Session log feed (during active sessions)
 * - Cross-device status: if a session is active on another device,
 *   this screen reflects it within 2 seconds via SessionContext polling.
 */

import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Platform,
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../../theme';
import { useSession } from '../../auth/SessionContext';
import { useProfiles } from '../../auth/ProfileContext';
import { useAuth } from '../../auth/AuthContext';
import {
  Chip,
  ChipRow,
  Divider,
  SectionLabel,
  SubscriptionBadge,
  Card,
  MonoBadge,
} from '../../components';
import PermissionBanner from '../../components/PermissionBanner';
import { useBlockingSetup } from '../../utils/useBlockingSetup';

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const min = Math.floor((s % 3600) / 60);
    return `${h}h ${String(min).padStart(2, '0')}m`;
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

export default function HomeScreen() {
  const navigation  = useNavigation<any>();
  const session     = useSession();
  const { activeProfile } = useProfiles();
  const { userInfo, signOut } = useAuth();

  const [goal,       setGoal]       = useState('');
  const [goalError,  setGoalError]  = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const { blockingStatus, requestPermission } = useBlockingSetup();

  // Pulse animation on session active state change
  React.useEffect(() => {
    if (session.isActive) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.4, duration: 900, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1,   duration: 900, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulseAnim.stopAnimation();
      pulseAnim.setValue(1);
    }
  }, [session.isActive]);

  // ── Session toggle ─────────────────────────────────────────────────────────
  const handleToggle = async () => {
    if (session.isActive) {
      await session.stopSession();
    } else {
      const g = goal.trim();
      if (!g) {
        setGoalError(true);
        setTimeout(() => setGoalError(false), 1200);
        return;
      }
      if (!activeProfile) return;
      await session.startSession({
        goal:            g,
        profile_name:    activeProfile.name,
        allowed_apps:    activeProfile.allowed_apps,
        banned_keywords: activeProfile.banned_keywords,
      });
    }
  };

  // ── "Started by other device" indicator ───────────────────────────────────
  const startedByOther = session.isActive
    && session.startedBy
    && !session.startedBy.includes('mobile');

  const displayName = userInfo?.display_name || userInfo?.email?.split('@')[0] || null;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <View style={styles.logoBox}>
              <Text style={styles.logoIcon}>∅</Text>
            </View>
            <Text style={styles.appName}>Nothing Alternative</Text>
            <Text style={styles.version}> v5</Text>
          </View>
          <View style={styles.headerRight}>
            <SubscriptionBadge
              status={session.subStatus}
              trialEndsAt={session.trialEndsAt}
              onPress={() => navigation.navigate('Pricing')}
            />
            {displayName && (
              <TouchableOpacity onPress={signOut} style={styles.userPill}>
                <Text style={styles.userPillText}>⬤  {displayName.slice(0, 12)}</Text>
              </TouchableOpacity>
            )}
            {/* Status dot */}
            <Animated.View
              style={[
                styles.statusDot,
                {
                  backgroundColor: session.isActive ? Colors.green : Colors.textMut,
                  opacity: session.isActive ? pulseAnim : 1,
                },
              ]}
            />
            <Text style={[styles.statusText, session.isActive && styles.statusTextActive]}>
              {session.isActive ? 'active' : 'idle'}
            </Text>
          </View>
        </View>

        <Divider style={styles.headerDivider} />

        {/* Permission banner (Android: Usage Access not granted) */}
        <PermissionBanner
          status={blockingStatus}
          onRequestAndroid={requestPermission}
        />

        {/* Cross-device banner */}
        {session.isActive && session.startedBy && (
          <View style={styles.crossDeviceBanner}>
            <Text style={styles.crossDeviceText}>
              Session active{session.startedBy ? ` · started by ${session.startedBy}` : ''}
            </Text>
          </View>
        )}

        {/* ── Goal ───────────────────────────────────────────────────────── */}
        <SectionLabel text="SESSION GOAL" />
        <View style={[styles.goalCard, goalError && styles.goalCardError]}>
          <Text style={styles.goalIcon}>✎</Text>
          <TextInput
            style={styles.goalInput}
            value={session.isActive ? (session.goal ?? '') : goal}
            onChangeText={setGoal}
            placeholder="What are you working on?"
            placeholderTextColor={Colors.textMut}
            editable={!session.isActive}
            maxLength={80}
            returnKeyType="done"
          />
          <Text style={styles.charCount}>
            {(session.isActive ? (session.goal?.length ?? 0) : goal.length)}/80
          </Text>
        </View>

        {/* ── Profile ────────────────────────────────────────────────────── */}
        <View style={styles.row}>
          <Text style={styles.rowLabel}>PROFILE</Text>
          <View style={styles.rowRight}>
            {activeProfile && (
              <MonoBadge text={`◈  ${activeProfile.name}`} />
            )}
            <TouchableOpacity onPress={() => navigation.navigate('Profiles')}>
              <Text style={styles.manageLink}>switch →</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* ── Allowed apps ───────────────────────────────────────────────── */}
        <View style={styles.rowHeader}>
          <Text style={styles.sectionLabelInline}>ALLOWED APPS</Text>
          <TouchableOpacity onPress={() => navigation.navigate('Settings')}>
            <Text style={styles.manageLink}>manage →</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.chipArea}>
          <ChipRow
            items={[
              ...((activeProfile?.allowed_apps ?? []).includes('browsers') ? ['All Browsers'] : []),
              ...(activeProfile?.allowed_apps ?? []).filter(a => 
                !['chrome','firefox','brave','browser','edge','opera','samsung',
                  'duckduckgo','vivaldi','yandex','tor','puffin','maxthon','browsers'].includes(a)
              )
            ]}
            variant="allowed"
          />
        </View>

        <Divider style={styles.sectionDiv} />

        {/* ── Blocked keywords ───────────────────────────────────────────── */}
        <View style={styles.rowHeader}>
          <Text style={styles.sectionLabelInline}>ALWAYS BLOCKED</Text>
          <TouchableOpacity onPress={() => navigation.navigate('Settings', { tab: 'blocked' })}>
            <Text style={styles.manageLink}>manage →</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.chipArea}>
          <ChipRow
            items={activeProfile?.banned_keywords ?? []}
            variant="blocked"
          />
        </View>

        <Divider style={styles.sectionDiv} />

        {/* ── Blocking methods ───────────────────────────────────────────── */}
        <SectionLabel text="BLOCKING METHODS" />
        <Card style={styles.methodsCard}>
          <View style={styles.methodRow}>
            <View style={[styles.methodDot, { backgroundColor: Colors.green }]} />
            <Text style={styles.methodText}>
              {Platform.OS === 'android'
                ? 'UsageStats · detects foreground app changes'
                : 'Screen Time · restricts apps during session'}
            </Text>
          </View>
          <View style={styles.methodRow}>
            <View style={[styles.methodDot, { backgroundColor: Colors.accent }]} />
            <Text style={styles.methodText}>
              Desktop extension · blocks tabs on your Mac/PC
            </Text>
          </View>
        </Card>

        {/* ── Session log ────────────────────────────────────────────────── */}
        {session.isActive && session.blockLog.length > 0 && (
          <>
            <SectionLabel text="SESSION LOG" />
            <Card style={styles.logCard}>
              {session.blockLog.slice(-20).map((entry, i) => (
                <Text
                  key={i}
                  style={[
                    styles.logEntry,
                    entry.type === 'app' ? styles.logBlocker : styles.logSniper,
                  ]}
                >
                  {entry.type === 'app' ? '[BLOCKER]' : '[SNIPER]'} {entry.name}
                </Text>
              ))}
            </Card>
          </>
        )}

        <View style={styles.bottomSpacer} />
      </ScrollView>

      {/* ── Fixed bottom bar ─────────────────────────────────────────────── */}
      <View style={styles.bottomBar}>
        <Divider />
        <View style={styles.metaRow}>
          <Text style={styles.metaText}>
            elapsed  {fmtElapsed(session.elapsedSeconds)}
          </Text>
          <Text style={styles.metaText}>
            blocked  {session.blockedCount}
          </Text>
        </View>
        {/* Progress bar */}
        <View style={styles.progressTrack}>
          <View
            style={[
              styles.progressFill,
              {
                width: session.isActive
                  ? `${((session.elapsedSeconds % 20) / 20) * 100}%`
                  : '0%',
              },
            ]}
          />
        </View>

        <TouchableOpacity
          style={[styles.sessionBtn, session.isActive && styles.sessionBtnStop]}
          onPress={handleToggle}
          activeOpacity={0.85}
        >
          <Text style={[styles.sessionBtnText, session.isActive && styles.sessionBtnTextStop]}>
            {session.isActive ? '■  Stop session' : '▶  Start session'}
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex:            1,
    backgroundColor: Colors.bgBase,
  },
  scroll: { flex: 1 },
  content: {
    paddingBottom: Spacing.xl,
  },

  // Header
  header: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.lg,
    paddingTop:     Spacing.md,
    paddingBottom:  Spacing.md,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           6,
  },
  logoBox: {
    width:        28,
    height:       28,
    borderWidth:  1,
    borderColor:  Colors.accent,
    borderRadius: Radius.sm,
    justifyContent: 'center',
    alignItems:     'center',
  },
  logoIcon: {
    fontFamily: Fonts.mono,
    fontSize:   13,
    color:      Colors.accent,
    fontWeight: 'bold',
  },
  appName: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },
  version: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           8,
  },
  userPill: {
    backgroundColor: Colors.bgRaised,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.pill,
    paddingHorizontal: 8,
    paddingVertical:   3,
  },
  userPillText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },
  statusDot: {
    width:        8,
    height:       8,
    borderRadius: 4,
  },
  statusText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },
  statusTextActive: { color: Colors.green },
  headerDivider: { marginTop: 0 },

  // Cross-device banner
  crossDeviceBanner: {
    backgroundColor: '#1a1a2e',
    borderBottomColor: Colors.border,
    borderBottomWidth: 1,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.xs,
  },
  crossDeviceText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.accent,
  },

  // Goal
  goalCard: {
    flexDirection:   'row',
    alignItems:      'center',
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    marginHorizontal: Spacing.lg,
    paddingHorizontal: Spacing.sm,
    height:          52,
  },
  goalCardError: { borderColor: Colors.red },
  goalIcon: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textMut,
    marginRight: 8,
  },
  goalInput: {
    flex:       1,
    color:      Colors.textPri,
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    height:     52,
  },
  charCount: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
    minWidth:   36,
    textAlign:  'right',
  },

  // Row / profile
  row: {
    flexDirection:   'row',
    alignItems:      'center',
    paddingHorizontal: Spacing.lg,
    marginTop:       Spacing.md,
    gap:             10,
  },
  rowLabel: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
    letterSpacing: 0.5,
  },
  rowRight: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           8,
  },
  manageLink: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.accent,
  },

  // Section headers
  rowHeader: {
    flexDirection:   'row',
    alignItems:      'center',
    justifyContent:  'space-between',
    paddingHorizontal: Spacing.lg,
    marginTop:       Spacing.md,
    marginBottom:    4,
  },
  sectionLabelInline: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
    letterSpacing: 0.5,
  },

  // Chip area
  chipArea: {
    paddingHorizontal: Spacing.lg,
  },

  sectionDiv: {
    marginTop:    Spacing.md,
    marginBottom: 0,
  },

  // Methods card
  methodsCard: {
    marginHorizontal: Spacing.lg,
    gap: 8,
  },
  methodRow: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           8,
  },
  methodDot: {
    width:        8,
    height:       8,
    borderRadius: 4,
  },
  methodText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textSec,
    flex:       1,
  },

  // Log
  logCard: {
    marginHorizontal: Spacing.lg,
    gap:              4,
  },
  logEntry: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    lineHeight: 16,
  },
  logSniper:  { color: Colors.logSniper },
  logBlocker: { color: Colors.logBlocker },

  bottomSpacer: { height: Spacing.xl },

  // Bottom bar
  bottomBar: {
    backgroundColor: Colors.bgBase,
    paddingHorizontal: Spacing.lg,
    paddingBottom:   Platform.OS === 'ios' ? Spacing.lg : Spacing.md,
    paddingTop:      Spacing.sm,
  },
  metaRow: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    marginBottom:   Spacing.sm,
    marginTop:      Spacing.sm,
  },
  metaText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },
  progressTrack: {
    height:          2,
    backgroundColor: Colors.border,
    borderRadius:    1,
    marginBottom:    Spacing.md,
    overflow:        'hidden',
  },
  progressFill: {
    height:          2,
    backgroundColor: Colors.accent,
    borderRadius:    1,
  },
  sessionBtn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.md,
    height:          52,
    justifyContent:  'center',
    alignItems:      'center',
  },
  sessionBtnStop: {
    backgroundColor: Colors.bgRaised,
    borderColor:     Colors.red,
    borderWidth:     1,
  },
  sessionBtnText: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },
  sessionBtnTextStop: { color: Colors.red },
});
