/**
 * BlockedScreen
 *
 * Shown inside the browser's custom tab / WebView when a domain is blocked.
 * Since we return NXDOMAIN from the VPN, the browser shows an error —
 * but we also catch the navigation event in any in-app WebView and render
 * this screen instead for a cleaner experience.
 *
 * For external browsers (Chrome etc.), the NXDOMAIN is enough to block.
 * This screen is primarily for any in-app WebView usage.
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  SafeAreaView,
} from 'react-native';
import { useSession } from '../auth/SessionContext';

interface Props {
  blockedDomain?: string;
  onDismiss?: () => void;
}

export function BlockedScreen({ blockedDomain, onDismiss }: Props) {
  const { goal } = useSession();

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <Text style={styles.icon}>🔒</Text>
        <Text style={styles.title}>Site blocked</Text>
        {blockedDomain ? (
          <Text style={styles.domain}>{blockedDomain}</Text>
        ) : null}
        <Text style={styles.body}>
          This site is blocked during your focus session
          {goal ? `: "${goal}"` : ''}.
        </Text>
        {onDismiss ? (
          <TouchableOpacity style={styles.button} onPress={onDismiss}>
            <Text style={styles.buttonText}>Go back</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  inner: {
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  icon: {
    fontSize: 48,
    marginBottom: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 8,
    letterSpacing: -0.5,
  },
  domain: {
    fontSize: 14,
    color: '#666666',
    marginBottom: 16,
    fontFamily: 'monospace',
  },
  body: {
    fontSize: 15,
    color: '#888888',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 32,
  },
  button: {
    backgroundColor: '#1A1A1A',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
  },
});
