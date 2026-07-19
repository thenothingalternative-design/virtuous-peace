/**
 * iOS Blocking — Screen Time API
 *
 * This module is the JS interface to the iOS Screen Time blocking layer.
 * The actual blocking is done by two iOS app extensions that must be added
 * to the Xcode project:
 *
 *   1. DeviceActivityMonitor extension
 *      - Monitors when a blocked app/category is used
 *      - Uses ManagedSettings to apply restrictions
 *
 *   2. (Optional) ShieldConfiguration extension
 *      - Customises the "blocked" screen shown by Screen Time
 *      - Shows the Nothing Alternative brand + goal
 *
 * Both extensions communicate with the main app via a shared App Group.
 *
 * This file:
 *   - Wraps the native FamilyControlsModule (Swift → RN bridge)
 *   - Provides requestAuthorization(), applyRestrictions(), clearRestrictions()
 *   - Falls back to Focus Filter guidance if entitlement is unavailable
 *
 * Requires in Xcode:
 *   - com.apple.developer.family-controls entitlement on the main target
 *   - App Group: group.com.nothingalternative.shared
 *   - DeviceActivity extension target
 */

import { Platform, NativeModules, Linking, Alert } from 'react-native';

// ── Native module interface ───────────────────────────────────────────────────
interface FamilyControlsNativeModule {
  requestAuthorization():        Promise<'approved' | 'denied'>;
  getAuthorizationStatus():      Promise<'approved' | 'denied' | 'notDetermined'>;
  applyRestrictions(config: {
    blockedBundleIds:  string[];  // e.g. ["com.google.ios.youtube"]
    blockedCategories: string[];  // Screen Time category tokens
    sessionGoal:       string;
  }): Promise<void>;
  clearRestrictions(): Promise<void>;
}

const { FamilyControlsModule } = NativeModules as {
  FamilyControlsModule?: FamilyControlsNativeModule;
};

// ── Well-known bundle IDs for common blocked apps ─────────────────────────────
// Maps keyword → iOS bundle ID so users don't have to know bundle IDs.
// This list covers the defaults from the desktop app.
const KEYWORD_TO_BUNDLE: Record<string, string> = {
  youtube:    'com.google.ios.youtube',
  facebook:   'com.facebook.Facebook',
  instagram:  'com.burbn.instagram',
  twitter:    'com.atebits.Tweetie2',
  'x.com':    'com.atebits.Tweetie2',
  reddit:     'com.reddit.Reddit',
  tiktok:     'com.zhiliaoapp.musically',
  netflix:    'com.netflix.Netflix',
  twitch:     'tv.twitch',
  snapchat:   'com.toyopagroup.picaboo',
  discord:    'com.hammerandchisel.discord',
  whatsapp:   'net.whatsapp.WhatsApp',
  telegram:   'ph.telegra.Telegraph',
  spotify:    'com.spotify.client',
  gmail:      'com.google.Gmail',
};

function keywordsToBundleIds(keywords: string[]): string[] {
  const ids: string[] = [];
  for (const kw of keywords) {
    const id = KEYWORD_TO_BUNDLE[kw.toLowerCase()];
    if (id) ids.push(id);
  }
  return [...new Set(ids)];
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function requestScreenTimeAuthorization(): Promise<boolean> {
  if (Platform.OS !== 'ios' || !FamilyControlsModule) return false;
  try {
    const status = await FamilyControlsModule.requestAuthorization();
    return status === 'approved';
  } catch {
    return false;
  }
}

export async function getScreenTimeAuthStatus(): Promise<'approved' | 'denied' | 'notDetermined' | 'unavailable'> {
  if (Platform.OS !== 'ios' || !FamilyControlsModule) return 'unavailable';
  try {
    return await FamilyControlsModule.getAuthorizationStatus();
  } catch {
    return 'unavailable';
  }
}

/**
 * Apply Screen Time restrictions for a focus session.
 * Blocks the apps matching `bannedKeywords` using ManagedSettings.
 * Falls back to Focus Filter guidance if FamilyControls is unavailable.
 */
export async function applyIOSBlocking(
  bannedKeywords: string[],
  goal: string,
): Promise<'screentime' | 'focusfilter' | 'unavailable'> {
  if (Platform.OS !== 'ios') return 'unavailable';

  // Try Screen Time API first
  if (FamilyControlsModule) {
    try {
      const status = await FamilyControlsModule.getAuthorizationStatus();
      if (status === 'notDetermined') {
        await FamilyControlsModule.requestAuthorization();
      }
      const currentStatus = await FamilyControlsModule.getAuthorizationStatus();
      if (currentStatus === 'approved') {
        const bundleIds = keywordsToBundleIds(bannedKeywords);
        await FamilyControlsModule.applyRestrictions({
          blockedBundleIds:  bundleIds,
          blockedCategories: ['SocialNetworking', 'Entertainment'],
          sessionGoal:       goal,
        });
        return 'screentime';
      }
    } catch (e) {
      console.warn('[iOS Blocking] Screen Time error:', e);
    }
  }

  // Fallback: guide user to enable Focus mode
  showFocusFilterGuidance(goal);
  return 'focusfilter';
}

export async function clearIOSBlocking(): Promise<void> {
  if (Platform.OS !== 'ios' || !FamilyControlsModule) return;
  try {
    await FamilyControlsModule.clearRestrictions();
  } catch (e) {
    console.warn('[iOS Blocking] clearRestrictions error:', e);
  }
}

// ── Focus Filter fallback ─────────────────────────────────────────────────────
// Shown when FamilyControls entitlement is unavailable or denied.
// Guides the user to enable their Nothing Alternative Focus mode.
function showFocusFilterGuidance(goal: string) {
  Alert.alert(
    'Enable Focus Mode',
    `For the strongest blocking on iOS, enable your "Nothing Alternative" Focus mode now.\n\nGo to: Settings → Focus → Nothing Alternative → Turn On\n\nOr ask Siri: "Turn on Nothing Alternative focus"`,
    [
      {
        text: 'Open Focus Settings',
        onPress: () => {
          // Deep link to Focus settings (iOS 15+)
          Linking.openURL('App-prefs:FOCUS').catch(() =>
            Linking.openURL('App-prefs:root=FOCUS')
          );
        },
      },
      { text: 'Later', style: 'cancel' },
    ]
  );
}

// ── Siri shortcut deep link ───────────────────────────────────────────────────
// Lets the user trigger a Nothing Alternative session via Siri.
export function openSiriShortcutSetup() {
  if (Platform.OS !== 'ios') return;
  // This would use expo-intent-launcher or a Shortcuts deep link
  // once the app has a Siri Intent defined.
  Linking.openURL('shortcuts://').catch(() => {});
}
