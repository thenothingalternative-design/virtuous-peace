/**
 * Android Blocking Service — UsageStatsManager & Overlay approach
 *
 * This module wraps the native Android UsageStatsManager so the JS layer
 * can poll for the current foreground app and show a blocking overlay
 * when a disallowed app comes to the foreground.
 *
 * Architecture:
 * JS layer (this file) ──polls every 1s──► native module ──► UsageStatsManager
 *
 * This file provides the JS wrapper + blocking logic that the HomeScreen,
 * SettingsScreen, and SessionContext can call.
 *
 * NOTE: This file is Android-only. It is never imported on iOS.
 */

import { NativeModules, Platform, Linking } from 'react-native';

// ── Native module interface ───────────────────────────────────────────────────
interface UsageStatsNativeModule {
  getForegroundApp():          Promise<string>;
  hasUsageStatsPermission():  Promise<boolean>;
  openUsageStatsSettings():   void;
  // Fallbacks for checking overlays natively if added later to the native module
  hasOverlayPermission?():    Promise<boolean>;
}

const { UsageStatsModule } = NativeModules as {
  UsageStatsModule: UsageStatsNativeModule | undefined;
};

// ── Public API ────────────────────────────────────────────────────────────────

export async function hasUsageStatsPermission(): Promise<boolean> {
  if (Platform.OS !== 'android' || !UsageStatsModule) return false;
  try {
    return await UsageStatsModule.hasUsageStatsPermission();
  } catch {
    return false;
  }
}

export function openUsageStatsSettings(): void {
  if (Platform.OS !== 'android' || !UsageStatsModule) return;
  UsageStatsModule.openUsageStatsSettings();
}

/**
 * Directs the user to the "Display over other apps" management screen.
 */
export async function openOverlayPermissionSettings(): Promise<void> {
  if (Platform.OS !== 'android') return;
  try {
    await Linking.sendIntent('android.settings.action.MANAGE_OVERLAY_PERMISSION');
  } catch (e) {
    console.error('Failed to open Overlay Settings intent, falling back to general settings:', e);
    await Linking.openSettings();
  }
}

/**
 * Checks if the system overlay window drawing permission is granted.
 */
export async function checkOverlayPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  
  // If your custom native module has an explicit checker, utilize it
  if (UsageStatsModule && typeof UsageStatsModule.hasOverlayPermission === 'function') {
    try {
      return await UsageStatsModule.hasOverlayPermission();
    } catch {
      return false;
    }
  }
  
  // Fail-closed fallback: default back to true if it hasn't crashed your setup yet,
  // or false to force setup compliance tracking.
  return false;
}

export async function getForegroundApp(): Promise<string | null> {
  if (Platform.OS !== 'android' || !UsageStatsModule) return null;
  try {
    return await UsageStatsModule.getForegroundApp();
  } catch {
    return null;
  }
}

// ── Blocking loop ─────────────────────────────────────────────────────────────
// Called by SessionContext when a session starts/stops on Android.
// Returns a cleanup function that stops polling.

type OnBlockCallback = (packageName: string) => void;

export function startBlockingLoop(
  bannedKeywords:  string[],
  allowedPackages: string[],
  onBlock: OnBlockCallback,
): () => void {
  if (Platform.OS !== 'android') return () => {};
  // Native Kotlin service handles the loop — nothing to do in JS
  return () => {};
}

/*export function startBlockingLoop(
  bannedKeywords:  string[],   // e.g. ["youtube", "reddit"]
  allowedPackages: string[],   // e.g. ["com.resolve", "com.spotify"]
  onBlock: OnBlockCallback,
): () => void {
  if (Platform.OS !== 'android') return () => {};

  let active = true;
  let intervalId: ReturnType<typeof setTimeout>;

  // Map banned keywords to partial package name matches
  const bannedPatterns = bannedKeywords.map(k => k.toLowerCase());
  const allowedPatterns = allowedPackages.map(p => p.toLowerCase());

  // System packages that are always allowed
  const SYSTEM_SAFE = [
    'com.android.launcher',
    'com.android.systemui',
    'com.nothing.alternative',
    'com.nothingalternative.app',
    'com.sec.android.app.launcher',          // Samsung
    'com.google.android.apps.nexuslauncher', // Pixel launcher
  ];

  const isBanned = (pkg: string): boolean => {
    const l = pkg.toLowerCase();
    return bannedPatterns.some(p => l.includes(p));
  };

  const isAllowed = (pkg: string): boolean => {
    const l = pkg.toLowerCase();
    if (SYSTEM_SAFE.some(s => l.includes(s))) return true;
    if (allowedPatterns.length === 0) return false;
    return allowedPatterns.some(p => l.includes(p) || p.includes(l));
  };

  const poll = async () => {
    if (!active) return;
    try {
      const pkg = await getForegroundApp();
      console.log('[POLL] foreground:', pkg);
      if (pkg && isBanned(pkg)) {
        onBlock(pkg);
      } else if (pkg && pkg !== '' && !isAllowed(pkg)) {
        onBlock(pkg);
      }
    } catch {}
    if (active) {
      intervalId = setTimeout(poll, 1000);
    }
  };

  // Start polling after a brief grace period
  intervalId = setTimeout(poll, 2000);

  return () => {
    active = false;
    clearTimeout(intervalId);
  };
}*/