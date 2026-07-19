/**
 * ProfilesScreen
 * Matches the desktop ProfilesPanel exactly.
 * Lists all focus profiles, lets user switch active, create new, delete.
 * All changes sync to the backend immediately.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  TextInput,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../../theme';
import { useProfiles } from '../../auth/ProfileContext';
import { useSession } from '../../auth/SessionContext';
import { Divider } from '../../components';

export default function ProfilesScreen() {
  const {
    profiles,
    activeProfile,
    setActiveProfile,
    createProfile,
    deleteProfile,
    isPremium,
  } = useProfiles() as any;
  const session = useSession();

  const [newName, setNewName] = useState('');

  const handleCreate = () => {
    const name = newName.trim();
    if (!name) return;

    // Free tier: 1 profile max (match desktop logic)
    const isPrem = session.isPremium;
    if (!isPrem && profiles.length >= 1) {
      Alert.alert(
        'Premium feature',
        'Free accounts support up to 1 profile.\nUpgrade to create unlimited profiles.',
        [
          { text: 'Maybe later', style: 'cancel' },
          { text: 'Upgrade →', onPress: () => {} /* navigate to Pricing */ },
        ]
      );
      return;
    }

    createProfile(name);
    setNewName('');
  };

  const handleDelete = (name: string) => {
    if (name === 'Default') return;
    Alert.alert(
      `Delete "${name}"?`,
      'This profile will be removed from all devices.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => deleteProfile(name),
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Focus Profiles</Text>
      </View>
      <Text style={styles.subtitle}>
        Each profile stores its own allowed-app list.
      </Text>

      <Divider style={styles.divider} />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {profiles.map((profile: any) => {
          const isActive = profile.name === activeProfile?.name;
          return (
            <View
              key={profile.name}
              style={[styles.profileCard, isActive && styles.profileCardActive]}
            >
              <View style={styles.profileLeft}>
                <View style={styles.profileNameRow}>
                  <Text style={[styles.profileName, isActive && styles.profileNameActive]}>
                    {profile.name}
                  </Text>
                  {isActive && (
                    <View style={styles.activeBadge}>
                      <Text style={styles.activeBadgeText}>active</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.profileMeta}>
                  {profile.allowed_apps.length} app{profile.allowed_apps.length !== 1 ? 's' : ''} allowed
                  {'  ·  '}
                  {profile.banned_keywords.length} site{profile.banned_keywords.length !== 1 ? 's' : ''} blocked
                </Text>
              </View>

              <View style={styles.profileActions}>
                {!isActive && (
                  <TouchableOpacity
                    style={styles.switchBtn}
                    onPress={() => setActiveProfile(profile.name)}
                    activeOpacity={0.8}
                  >
                    <Text style={styles.switchBtnText}>Switch</Text>
                  </TouchableOpacity>
                )}
                {profile.name !== 'Default' && (
                  <TouchableOpacity
                    style={styles.deleteBtn}
                    onPress={() => handleDelete(profile.name)}
                    activeOpacity={0.8}
                  >
                    <Text style={styles.deleteBtnText}>Delete</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          );
        })}

        <Divider style={styles.footerDivider} />

        {/* Create new profile */}
        <View style={styles.createSection}>
          <Text style={styles.createLabel}>New profile name:</Text>
          <View style={styles.createRow}>
            <TextInput
              style={styles.createInput}
              value={newName}
              onChangeText={setNewName}
              placeholder="e.g. Deep Work, Study…"
              placeholderTextColor={Colors.textMut}
              onSubmitEditing={handleCreate}
              returnKeyType="done"
              autoCapitalize="words"
            />
            <TouchableOpacity
              style={styles.createBtn}
              onPress={handleCreate}
              activeOpacity={0.8}
            >
              <Text style={styles.createBtnText}>Create</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex:            1,
    backgroundColor: Colors.bgBase,
  },
  header: {
    paddingHorizontal: Spacing.lg,
    paddingTop:        Spacing.md,
    paddingBottom:     Spacing.sm,
  },
  title: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.xl,
    color:      Colors.textPri,
  },
  subtitle: {
    fontFamily:      Fonts.sans,
    fontSize:        FontSizes.sm,
    color:           Colors.textMut,
    paddingHorizontal: Spacing.lg,
    marginBottom:    Spacing.sm,
  },
  divider: {},
  scroll:  { flex: 1 },
  content: {
    padding: Spacing.lg,
    gap:     Spacing.sm,
  },

  // Profile card
  profileCard: {
    flexDirection:   'row',
    alignItems:      'center',
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    padding:         Spacing.md,
  },
  profileCardActive: {
    backgroundColor: Colors.bgRaised,
    borderColor:     Colors.accent,
  },
  profileLeft: {
    flex: 1,
    gap:  4,
  },
  profileNameRow: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           8,
  },
  profileName: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textSec,
  },
  profileNameActive: { color: Colors.textPri },
  activeBadge: {
    backgroundColor: '#1a2a1a',
    borderColor:     '#336633',
    borderWidth:     1,
    borderRadius:    Radius.sm,
    paddingHorizontal: 6,
    paddingVertical:   2,
  },
  activeBadgeText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      '#44aa44',
  },
  profileMeta: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },
  profileActions: {
    flexDirection: 'row',
    gap:           8,
  },
  switchBtn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.sm,
    paddingHorizontal: 14,
    paddingVertical:   7,
  },
  switchBtnText: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.textPri,
  },
  deleteBtn: {
    backgroundColor: Colors.bgRaised,
    borderColor:     Colors.red,
    borderWidth:     1,
    borderRadius:    Radius.sm,
    paddingHorizontal: 12,
    paddingVertical:   7,
  },
  deleteBtnText: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.red,
  },

  footerDivider: { marginVertical: Spacing.md },

  // Create section
  createSection: { gap: 8 },
  createLabel: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.textMut,
  },
  createRow: {
    flexDirection: 'row',
    gap:           8,
  },
  createInput: {
    flex:            1,
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.sm,
    color:           Colors.textPri,
    fontFamily:      Fonts.sans,
    fontSize:        FontSizes.md,
    height:          40,
    paddingHorizontal: Spacing.sm,
  },
  createBtn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.sm,
    paddingHorizontal: 16,
    justifyContent:  'center',
    alignItems:      'center',
    height:          40,
  },
  createBtnText: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },
});
