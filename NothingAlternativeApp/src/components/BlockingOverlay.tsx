/**
 * BlockingOverlay
 *
 * Full-screen overlay shown on Android when the blocking loop detects
 * a disallowed app in the foreground.
 *
 * Rendered as a modal over the entire app. The user can only dismiss it
 * by stopping their session — there's no other way out.
 *
 * Usage: render this in App.tsx, controlled by BlockingOverlayContext.
 */

import React from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Linking, 
  BackHandler,
} from 'react-native';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../theme';
import { useSession } from '../auth/SessionContext';

interface BlockingOverlayProps {
  visible:     boolean;
  blockedApp:  string;
  onDismiss:   () => void;  // called after session stopped
}

export default function BlockingOverlay({
  visible,
  blockedApp,
  onDismiss,
}: BlockingOverlayProps) {
  const session = useSession();

  // Intercept Android hardware back button — don't let user escape
  React.useEffect(() => {
    if (!visible) return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => true); // consume
    return () => sub.remove();
  }, [visible]);

  return (
    <Modal
      visible={visible}
      animationType="fade"
      statusBarTranslucent
      transparent={false}
    >
      <View style={styles.container}>
        {/* Logo */}
        <View style={styles.logoBox}>
          <Text style={styles.logoIcon}>∅</Text>
        </View>

        {/* Heading */}
        <Text style={styles.heading}>Blocked</Text>
        <Text style={styles.appName} numberOfLines={1}>
          {blockedApp.split('.').pop() ?? blockedApp}
        </Text>

        {/* Message */}
        <Text style={styles.message}>
          This app isn't allowed during your focus session.{'\n'}
          Return to your work or stop the session.
        </Text>

        {/* Session info */}
        {session.goal && (
          <View style={styles.goalCard}>
            <Text style={styles.goalLabel}>Current goal</Text>
            <Text style={styles.goal}>{session.goal}</Text>
          </View>
        )}

        {/* Elapsed */}
        <Text style={styles.elapsed}>
          {formatElapsed(session.elapsedSeconds)} focused  ·  {session.blockedCount} blocked
        </Text>

        <TouchableOpacity
          style={styles.returnBtn}
          onPress={() => { onDismiss(); BackHandler.exitApp(); }}
          activeOpacity={0.85}
        >
          <Text style={styles.returnBtnText}>← Get back to work</Text> 
        </TouchableOpacity>

        <Text style={styles.hint}>
          To stop your session, open Nothing Alternative.
        </Text>
      </View>
    </Modal>
  );
}

function formatElapsed(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const min = Math.floor((s % 3600) / 60);
    return `${h}h ${String(min).padStart(2, '0')}m`;
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

const styles = StyleSheet.create({
  container: {
    flex:            1,
    backgroundColor: Colors.bgBase,
    alignItems:      'center',
    justifyContent:  'center',
    padding:         Spacing.xl,
    gap:             Spacing.md,
  },

  logoBox: {
    width:        64,
    height:       64,
    borderWidth:  1,
    borderColor:  Colors.red,
    borderRadius: Radius.lg,
    justifyContent: 'center',
    alignItems:     'center',
    marginBottom:   Spacing.sm,
  },
  logoIcon: {
    fontFamily: Fonts.mono,
    fontSize:   28,
    color:      Colors.red,
    fontWeight: 'bold',
  },

  heading: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.h1,
    color:      Colors.red,
  },
  appName: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.lg,
    color:      Colors.textSec,
    textTransform: 'lowercase',
  },
  message: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textSec,
    textAlign:  'center',
    lineHeight: 22,
    maxWidth:   320,
  },

  goalCard: {
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    padding:         Spacing.md,
    width:           '100%',
    maxWidth:        320,
    gap:             4,
  },
  goalLabel: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
    letterSpacing: 0.5,
  },
  goal: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },

  elapsed: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.sm,
    color:      Colors.textMut,
  },

  returnBtn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.md,
    height:          52,
    width:           '100%',
    maxWidth:        320,
    justifyContent:  'center',
    alignItems:      'center',
    marginTop:       Spacing.sm,
  },
  returnBtnText: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },
  stopLink: {
    marginTop: Spacing.sm,
    padding:   Spacing.sm,
  },
  stopLinkText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },

  hint: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.textMut,
    textAlign:  'center',
  },
});
