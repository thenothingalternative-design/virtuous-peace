/**
 * SignInScreen
 *
 * Google Sign-In → POST /auth/google → store JWT
 * Apple Sign-In  → POST /auth/apple  → store JWT  (iOS only, required by App Store)
 * Offline mode   → skip auth entirely
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Platform,
  ActivityIndicator,
  ScrollView,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../../theme';
import { useAuth } from '../../auth/AuthContext';
import { authGoogle, authApple } from '../../api';

// ── Platform-conditional imports ─────────────────────────────────────────────
// These are resolved at build time; the app never crashes if a module is missing.
let GoogleSignin: any = null;
let AppleAuthentication: any = null;

try {
  GoogleSignin = require('@react-native-google-signin/google-signin').GoogleSignin;
  GoogleSignin.configure({
    // Replace with your actual Web client ID from Google Cloud Console
  webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID,    
  scopes: ['profile', 'email'],
  });
} catch {}

try {
  AppleAuthentication = require('expo-apple-authentication');
} catch {}

export default function SignInScreen() {
  const { signIn, skipAuth } = useAuth();
  const [loading, setLoading] = useState<'google' | 'apple' | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  // ── Google sign-in ────────────────────────────────────────────────────────
    const handleGoogle = async () => {
    if (!GoogleSignin) {
      setError('Google Sign-In is not configured in this build.');
      return;
    }
    setLoading('google');
    setError(null);
    try {
      await GoogleSignin.hasPlayServices();
      await GoogleSignin.signIn();
      const tokens = await GoogleSignin.getTokens();
      const idToken = tokens.idToken;
      if (!idToken) throw new Error('No ID token from Google');
      const tokenData = await authGoogle(idToken);
      if (!tokenData) throw new Error('Backend sign-in failed');
      await signIn(tokenData);
    } catch (e: any) {
      if (e?.code !== 'SIGN_IN_CANCELLED') {
        setError(e?.message ?? 'Google sign-in failed. Please try again.');
      }
    } finally {
      setLoading(null);
    }
  };

  // ── Apple sign-in (iOS only) ───────────────────────────────────────────────
  const handleApple = async () => {
    if (!AppleAuthentication) {
      setError('Apple Sign-In is not available on this device.');
      return;
    }
    setLoading('apple');
    setError(null);
    try {
      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      const { identityToken, email, fullName } = credential;
      if (!identityToken) throw new Error('No identity token from Apple');
      const displayName = [fullName?.givenName, fullName?.familyName]
        .filter(Boolean).join(' ') || null;
      const tokenData = await authApple(identityToken, email, displayName);
      if (!tokenData) throw new Error('Backend sign-in failed');
      await signIn(tokenData);
    } catch (e: any) {
      if (e?.code !== 'ERR_REQUEST_CANCELED') {
        setError(e?.message ?? 'Apple sign-in failed. Please try again.');
      }
    } finally {
      setLoading(null);
    }
  };

  const showApple = Platform.OS === 'ios' && !!AppleAuthentication;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">

        {/* Logo */}
        <View style={styles.logoSection}>
          <View style={styles.logoBox}>
            <Text style={styles.logoIcon}>∅</Text>
          </View>
          <Text style={styles.appName}>Nothing Alternative</Text>
          <Text style={styles.tagline}>Sign in to sync sessions across devices</Text>
        </View>

        {/* Auth card */}
        <View style={styles.card}>

          {/* Google */}
          <TouchableOpacity
            style={styles.googleBtn}
            onPress={handleGoogle}
            activeOpacity={0.8}
            disabled={loading !== null}
          >
            {loading === 'google' ? (
              <ActivityIndicator color={Colors.textPri} />
            ) : (
              <>
                <Text style={styles.googleG}>G</Text>
                <Text style={styles.googleLabel}>Continue with Google</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Apple (iOS only) */}
          {showApple && (
            <TouchableOpacity
              style={styles.appleBtn}
              onPress={handleApple}
              activeOpacity={0.8}
              disabled={loading !== null}
            >
              {loading === 'apple' ? (
                <ActivityIndicator color={Colors.bgBase} />
              ) : (
                <>
                  <Text style={styles.appleLogo}></Text>
                  <Text style={styles.appleLabel}>Continue with Apple</Text>
                </>
              )}
            </TouchableOpacity>
          )}

          {/* Divider */}
          <View style={styles.dividerRow}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>

          {/* Offline */}
          <TouchableOpacity
            style={styles.offlineBtn}
            onPress={skipAuth}
            activeOpacity={0.7}
            disabled={loading !== null}
          >
            <Text style={styles.offlineLabel}>Use offline (no sync)</Text>
          </TouchableOpacity>

          {/* Error */}
          {error && <Text style={styles.error}>{error}</Text>}
        </View>

        {/* Fine print */}
        <Text style={styles.finePrint}>
          Your data stays on your device in offline mode.{'\n'}
          Sign in to sync profiles &amp; history across all devices.
        </Text>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex:            1,
    backgroundColor: Colors.bgBase,
  },
  container: {
    flexGrow:       1,
    justifyContent: 'center',
    alignItems:     'center',
    padding:        Spacing.lg,
  },

  // Logo
  logoSection: {
    alignItems:    'center',
    marginBottom:  Spacing.xl,
  },
  logoBox: {
    width:        52,
    height:       52,
    borderWidth:  1,
    borderColor:  Colors.accent,
    borderRadius: Radius.lg,
    justifyContent: 'center',
    alignItems:     'center',
    marginBottom:   Spacing.md,
  },
  logoIcon: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xl,
    color:      Colors.accent,
    fontWeight: 'bold',
  },
  appName: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.xxl,
    color:      Colors.textPri,
    marginBottom: 6,
  },
  tagline: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textSec,
    textAlign:  'center',
  },

  // Card
  card: {
    width:           '100%',
    maxWidth:        380,
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.lg,
    padding:         Spacing.lg,
    gap:             Spacing.sm,
  },

  // Google button
  googleBtn: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'center',
    backgroundColor: Colors.bgRaised,
    borderColor:    Colors.border,
    borderWidth:    1,
    borderRadius:   Radius.md,
    height:         48,
    gap:            10,
  },
  googleG: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.lg,
    color:      '#4285F4',
  },
  googleLabel: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },

  // Apple button
  appleBtn: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'center',
    backgroundColor: Colors.textPri,
    borderRadius:   Radius.md,
    height:         48,
    gap:            10,
  },
  appleLogo: {
    fontSize:   FontSizes.lg,
    color:      Colors.bgBase,
    lineHeight: 22,
  },
  appleLabel: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.bgBase,
  },

  // Divider
  dividerRow: {
    flexDirection:  'row',
    alignItems:     'center',
    gap:            Spacing.sm,
    marginVertical: Spacing.xs,
  },
  dividerLine: {
    flex:            1,
    height:          1,
    backgroundColor: Colors.border,
  },
  dividerText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },

  // Offline button
  offlineBtn: {
    alignItems:     'center',
    justifyContent: 'center',
    borderColor:    Colors.border,
    borderWidth:    1,
    borderRadius:   Radius.md,
    height:         44,
  },
  offlineLabel: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textMut,
  },

  // Error
  error: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.amber,
    textAlign:  'center',
    marginTop:  Spacing.xs,
  },

  // Fine print
  finePrint: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.textMut,
    textAlign:  'center',
    marginTop:  Spacing.lg,
    lineHeight: 18,
  },
});
