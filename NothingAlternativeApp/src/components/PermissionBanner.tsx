/**
 * PermissionBanner
 *
 * Shown at the top of the Home screen when:
 *   - Android: Usage Access permission not granted
 *   - iOS: FamilyControls not yet authorized (before first session)
 *
 * Dismisses permanently once permission is granted.
 */

import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Platform,
} from 'react-native';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../theme';
import { BlockingStatus } from '../utils/useBlockingSetup';

interface PermissionBannerProps {
  status:          BlockingStatus;
  onRequestAndroid: () => void;
}

export default function PermissionBanner({
  status,
  onRequestAndroid,
}: PermissionBannerProps) {
  if (status !== 'permission_needed') return null;

  if (Platform.OS === 'android') {
    return (
      <TouchableOpacity style={styles.banner} onPress={onRequestAndroid} activeOpacity={0.8}>
        <View style={styles.row}>
          <View style={[styles.dot, { backgroundColor: Colors.amber }]} />
          <View style={styles.textCol}>
            <Text style={styles.title}>Grant Usage Access</Text>
            <Text style={styles.body}>
              Required for Nothing Alternative to detect and block distracting apps
              during focus sessions.{'\n'}Tap to open Settings.
            </Text>
          </View>
          <Text style={styles.arrow}>›</Text>
        </View>
      </TouchableOpacity>
    );
  }

  return null;
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: '#1a1500',
    borderColor:     '#3a3000',
    borderWidth:     1,
    borderRadius:    Radius.md,
    marginHorizontal: Spacing.lg,
    marginTop:       Spacing.sm,
    padding:         Spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems:    'flex-start',
    gap:           Spacing.sm,
  },
  dot: {
    width:     8,
    height:    8,
    borderRadius: 4,
    marginTop: 4,
  },
  textCol: {
    flex: 1,
    gap:  3,
  },
  title: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.sm,
    color:      Colors.amber,
  },
  body: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.textSec,
    lineHeight: 18,
  },
  arrow: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.lg,
    color:      Colors.amber,
    alignSelf:  'center',
  },
});
