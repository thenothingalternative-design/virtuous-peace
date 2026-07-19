/**
 * SettingsScreen
 *
 * Two tabs: Allowed Apps | Blocked Sites
 *
 * Android: calls UsageStatsModule.getInstalledApps() — our own native module,
 *          no third-party package needed.
 * iOS:     manual add only (app enumeration not allowed by platform).
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Switch,
  Platform,
  TextInput,
  ActivityIndicator,
  NativeModules,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../../theme';
import { useProfiles } from '../../auth/ProfileContext';
import { Divider, AddItemRow } from '../../components';
import { openUsageStatsSettings, openOverlayPermissionSettings } from '../../utils/androidBlocking';

// ── Tab selector ──────────────────────────────────────────────────────────────
function TabBar({
  active,
  onChange,
}: {
  active:   'apps' | 'blocked';
  onChange: (tab: 'apps' | 'blocked') => void;
}) {
  return (
    <View style={tabStyles.bar}>
      {(['apps', 'blocked'] as const).map(tab => (
        <TouchableOpacity
          key={tab}
          style={[tabStyles.tab, active === tab && tabStyles.tabActive]}
          onPress={() => onChange(tab)}
          activeOpacity={0.7}
        >
          <Text style={[tabStyles.tabText, active === tab && tabStyles.tabTextActive]}>
            {tab === 'apps' ? 'Allowed Apps' : 'Blocked Sites'}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const tabStyles = StyleSheet.create({
  bar: {
    flexDirection:    'row',
    marginHorizontal: Spacing.lg,
    marginVertical:   Spacing.sm,
    backgroundColor:  Colors.bgSurface,
    borderRadius:     Radius.md,
    padding:          3,
    gap:              3,
  },
  tab:          { flex: 1, paddingVertical: 8, borderRadius: Radius.sm, alignItems: 'center' },
  tabActive:    { backgroundColor: Colors.bgRaised },
  tabText:      { fontFamily: Fonts.mono, fontSize: FontSizes.xs, color: Colors.textMut },
  tabTextActive:{ color: Colors.textPri },
});

const BROWSER_PACKAGES = [
  'com.android.chrome',
  'com.microsoft.emmx',
  'com.brave.browser',
  'org.mozilla.firefox',
  'com.opera.browser',
  'com.sec.android.app.sbrowser',
  'com.duckduckgo.mobile.android',
  'com.kiwibrowser.browser',
];

// ── Android: Allowed Apps tab ─────────────────────────────────────────────────
function AndroidAppsTab() {
  const { activeProfile, addAllowedApp, removeAllowedApp } = useProfiles();
  const [apps, setApps] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  
  // Track BOTH permissions independently
  const [hasUsagePermission, setHasUsagePermission] = useState(false);
  const [hasOverlayPermission, setHasOverlayPermission] = useState(false);

  useEffect(() => {
    checkAndLoad();
  }, []);

  const checkAndLoad = async () => {
    const { UsageStatsModule } = NativeModules;
    if (!UsageStatsModule) return;

    // Check Usage Stats
    const usageGranted = await UsageStatsModule.hasUsageStatsPermission().catch(() => false);
    setHasUsagePermission(usageGranted);

    // Check Overlay Draw capabilities
    const overlayGranted = await UsageStatsModule.hasOverlayPermission().catch(() => false);
    setHasOverlayPermission(overlayGranted);

    setLoading(true);
    try {
      const list: any[] = await UsageStatsModule.getInstalledApps();
      const sorted = list.sort((a, b) =>
        (a.appName ?? '').localeCompare(b.appName ?? '')
      );
      setApps(sorted);
      console.log('PACKAGES:', sorted.map((a: any) => a.packageName).join('\n'));
    } catch (e) {
      console.warn('[SettingsScreen] getInstalledApps error:', e);
    } finally {
      setLoading(false);
    }
  };

  const allowed = new Set(activeProfile?.allowed_apps ?? []);
  const filtered = apps.filter(a =>
    !BROWSER_PACKAGES.includes(a.packageName) && (
      !query ||
      (a.appName ?? '').toLowerCase().includes(query.toLowerCase()) ||
      (a.hint ?? '').toLowerCase().includes(query.toLowerCase())
    )
  );

  const isOn = (app: any): boolean => {
    const h = app.hint ?? '';
    return allowed.has(h) || [...allowed].some(a => a.includes(h) || h.includes(a));
  };

  // Determine what banner to show and action to take dynamically
  const isFullyConfigured = hasUsagePermission && hasOverlayPermission;
  
  const handleBannerPress = () => {
    if (!hasUsagePermission) {
      openUsageStatsSettings();
    } else if (!hasOverlayPermission) {
      openOverlayPermissionSettings();
    }
  };

  const getBannerText = () => {
    if (!hasUsagePermission) return 'Tap to grant Usage Access (required for tracking)';
    if (!hasOverlayPermission) return 'Usage granted. Tap to grant Draw Over Apps (required to block)';
    return 'Shield active — App detection and blocking fully functional';
  };

  return (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={appTabStyles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* Dynamic Permission Banner */}
      <TouchableOpacity 
        style={appTabStyles.permBanner} 
        onPress={handleBannerPress}
      >
        <View style={[
          appTabStyles.permDot, 
          { backgroundColor: isFullyConfigured ? Colors.green : Colors.amber }
        ]} />
        <Text style={appTabStyles.permText}>
          {getBannerText()}
        </Text>
      </TouchableOpacity>

      {/* Search Row */}
      <View style={appTabStyles.searchRow}>
        <TextInput
          style={appTabStyles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search installed apps…"
          placeholderTextColor={Colors.textMut}
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>

      {loading && <ActivityIndicator color={Colors.accent} style={{ marginTop: Spacing.md }} />}

      {/* All Browsers row */}
      <View style={appTabStyles.row}>
        <View style={appTabStyles.rowInfo}>
          <Text style={appTabStyles.appName}>All Browsers</Text>
          <Text style={appTabStyles.appPkg}>chrome, firefox, brave, edge + more</Text>
        </View>
        <Switch
          value={(activeProfile?.allowed_apps ?? []).includes('browsers')}
          onValueChange={v => {
            if (v) {
              addAllowedApp('browsers');
            } else {
              removeAllowedApp('browsers');
            }
          }}
          trackColor={{ false: Colors.border, true: Colors.accent }}
          thumbColor={Colors.textPri}
        />
      </View>

      {filtered.map((app: any) => (
        <View key={app.packageName} style={appTabStyles.row}>
          <View style={appTabStyles.rowInfo}>
            <Text style={appTabStyles.appName}>{app.appName}</Text>
            <Text style={appTabStyles.appPkg}>{app.hint}</Text>
          </View>
          <Switch
            value={isOn(app)}
            onValueChange={v =>
              v ? addAllowedApp(app.packageName) : removeAllowedApp(app.packageName)
            }
            trackColor={{ false: Colors.border, true: Colors.accent }}
            thumbColor={Colors.textPri}
          />
        </View>
      ))}

      <Divider style={{ marginVertical: Spacing.md }} />
      <Text style={appTabStyles.manualLabel}>Can't find it? Add manually:</Text>
      <AddItemRow
        placeholder="e.g. spotify, notion"
        onAdd={addAllowedApp}
        buttonColor={Colors.accent}
      />
    </ScrollView>
  );
}

const appTabStyles = StyleSheet.create({
  content:      { padding: Spacing.lg, gap: 8 },
  permBanner:   {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.bgRaised, borderRadius: Radius.sm,
    padding: Spacing.sm, gap: 8, marginBottom: Spacing.sm,
  },
  permDot:      { width: 8, height: 8, borderRadius: 4 },
  permText:     { fontFamily: Fonts.mono, fontSize: FontSizes.xs, color: Colors.textSec, flex: 1 },
  searchRow:    {
    backgroundColor: Colors.bgSurface, borderColor: Colors.border, borderWidth: 1,
    borderRadius: Radius.md, paddingHorizontal: Spacing.sm, height: 44,
    justifyContent: 'center', marginBottom: Spacing.sm,
  },
  searchInput:  { color: Colors.textPri, fontFamily: Fonts.sans, fontSize: FontSizes.md },
  row:          {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: 10, borderBottomColor: Colors.border, borderBottomWidth: 1,
  },
  rowInfo:      { flex: 1, gap: 2 },
  appName:      { fontFamily: Fonts.sans,  fontSize: FontSizes.md, color: Colors.textPri },
  appPkg:       { fontFamily: Fonts.mono,  fontSize: FontSizes.xs, color: Colors.textMut },
  manualLabel:  { fontFamily: Fonts.sans,  fontSize: FontSizes.sm, color: Colors.textMut, marginBottom: 6 },
});

// ── iOS / manual: Allowed Apps tab ────────────────────────────────────────────
function ManualAppsTab() {
  const { activeProfile, addAllowedApp, removeAllowedApp } = useProfiles();
  const apps = activeProfile?.allowed_apps ?? [];

  return (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ padding: Spacing.lg, gap: Spacing.sm }}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={manualStyles.info}>
        iOS doesn't allow reading installed apps.{'\n'}
        Add app names manually — use the name you'd type to search for the app.
      </Text>

      {apps.map(app => (
        <View key={app} style={manualStyles.row}>
          <Text style={manualStyles.appName}>{app}</Text>
          <TouchableOpacity onPress={() => removeAllowedApp(app)}>
            <Text style={manualStyles.removeBtn}>Remove</Text>
          </TouchableOpacity>
        </View>
      ))}

      {apps.length === 0 && (
        <Text style={manualStyles.empty}>No apps allowed — everything outside the session is blocked.</Text>
      )}

      <Divider style={{ marginVertical: Spacing.sm }} />
      <AddItemRow
        placeholder="e.g. spotify, notion, figma"
        onAdd={addAllowedApp}
        buttonColor={Colors.accent}
      />
    </ScrollView>
  );
}

const manualStyles = StyleSheet.create({
  info:      { fontFamily: Fonts.sans, fontSize: FontSizes.sm, color: Colors.textMut, lineHeight: 18, marginBottom: Spacing.sm },
  row:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: Colors.bgSurface, borderColor: Colors.border, borderWidth: 1, borderRadius: Radius.sm, padding: Spacing.sm },
  appName:   { fontFamily: Fonts.mono, fontSize: FontSizes.md, color: Colors.textPri },
  removeBtn: { fontFamily: Fonts.sans, fontSize: FontSizes.sm, color: Colors.red },
  empty:     { fontFamily: Fonts.mono, fontSize: FontSizes.xs, color: Colors.textMut, textAlign: 'center', marginTop: Spacing.md },
});

// ── Blocked sites tab ─────────────────────────────────────────────────────────
function BlockedTab() {
  const { activeProfile, addBlockedKeyword, removeBlockedKeyword } = useProfiles();
  const keywords = activeProfile?.banned_keywords ?? [];

  return (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ padding: Spacing.lg, gap: Spacing.sm }}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={blockedStyles.info}>
        These keywords block browser tabs on your Mac/PC.{'\n'}
        On mobile, matching apps are blocked during a session.
      </Text>

      {keywords.map(kw => (
        <View key={kw} style={blockedStyles.row}>
          <Text style={blockedStyles.kw}>⊘  {kw}</Text>
          <TouchableOpacity style={blockedStyles.removeBtn} onPress={() => removeBlockedKeyword(kw)}>
            <Text style={blockedStyles.removeBtnText}>Remove</Text>
          </TouchableOpacity>
        </View>
      ))}

      {keywords.length === 0 && (
        <Text style={blockedStyles.empty}>No sites blocked yet.</Text>
      )}

      <Divider style={{ marginVertical: Spacing.sm }} />
      <Text style={blockedStyles.addLabel}>Add a site or keyword:</Text>
      <AddItemRow
        placeholder="e.g. twitch.tv, hacker news"
        onAdd={addBlockedKeyword}
        buttonColor={Colors.red}
        buttonLabel="Block"
      />
    </ScrollView>
  );
}

const blockedStyles = StyleSheet.create({
  info:          { fontFamily: Fonts.sans, fontSize: FontSizes.sm, color: Colors.textMut, lineHeight: 18, marginBottom: Spacing.sm },
  row:           { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: Colors.bgSurface, borderColor: Colors.border, borderWidth: 1, borderRadius: Radius.sm, paddingHorizontal: Spacing.sm, paddingVertical: 10 },
  kw:            { fontFamily: Fonts.mono, fontSize: FontSizes.sm, color: '#aa4455' },
  removeBtn:     { backgroundColor: Colors.bgRaised, borderColor: Colors.red, borderWidth: 1, borderRadius: Radius.sm, paddingHorizontal: 10, paddingVertical: 4 },
  removeBtnText: { fontFamily: Fonts.sans, fontSize: FontSizes.sm, color: Colors.red },
  empty:         { fontFamily: Fonts.mono, fontSize: FontSizes.xs, color: Colors.textMut, textAlign: 'center', marginTop: Spacing.md },
  addLabel:      { fontFamily: Fonts.sans, fontSize: FontSizes.sm, color: Colors.textMut, marginBottom: 6 },
});

// ── Main screen ───────────────────────────────────────────────────────────────
export default function SettingsScreen({ route }: any) {
  const initialTab = route?.params?.tab === 'blocked' ? 'blocked' : 'apps';
  const [activeTab, setActiveTab] = useState<'apps' | 'blocked'>(initialTab);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Settings</Text>
      </View>
      <Divider />
      <TabBar active={activeTab} onChange={setActiveTab} />
      {activeTab === 'apps'
        ? (Platform.OS === 'android' ? <AndroidAppsTab /> : <ManualAppsTab />)
        : <BlockedTab />}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bgBase },
  header: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.md, paddingBottom: Spacing.md },
  title:  { fontFamily: Fonts.sansBold, fontSize: FontSizes.xl, color: Colors.textPri },
});
