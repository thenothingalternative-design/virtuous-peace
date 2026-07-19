/**
 * HistoryScreen
 * Matches the desktop HistoryPanel.
 * Fetches from /sessions/history on mount, merges with local history.
 * Shows: summary stat cards, most-blocked chart, per-session rows.
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../../theme';
import { getHistory, SessionOut } from '../../api';
import { Divider, Card } from '../../components';

function fmtDur(s: number): string {
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h ${String(m).padStart(2, '0')}m`;
  }
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}m ${String(sec).padStart(2, '0')}s`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

// Mini horizontal bar chart for most-blocked items
function MiniChart({
  title,
  color,
  items,
}: {
  title: string;
  color: string;
  items: [string, number][];
}) {
  if (items.length === 0) return null;
  const max = items[0][1];
  return (
    <View style={chartStyles.container}>
      <Text style={[chartStyles.title, { color }]}>{title}</Text>
      {items.slice(0, 5).map(([name, count]) => (
        <View key={name} style={chartStyles.row}>
          <Text style={chartStyles.name} numberOfLines={1}>{name.slice(0, 16)}</Text>
          <View style={chartStyles.barTrack}>
            <View style={[chartStyles.bar, { backgroundColor: color, width: `${(count / max) * 100}%` }]} />
          </View>
          <Text style={chartStyles.count}>{count}</Text>
        </View>
      ))}
    </View>
  );
}

const chartStyles = StyleSheet.create({
  container: {
    flex:  1,
    gap:   4,
  },
  title: {
    fontFamily:   Fonts.mono,
    fontSize:     FontSizes.xs,
    marginBottom: 4,
  },
  row: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           6,
  },
  name: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textPri,
    width:      80,
  },
  barTrack: {
    flex:            1,
    height:          8,
    backgroundColor: Colors.bgRaised,
    borderRadius:    4,
    overflow:        'hidden',
  },
  bar: {
    height:       8,
    borderRadius: 4,
  },
  count: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
    width:      20,
    textAlign:  'right',
  },
});

// Per-session row
function SessionRow({ session }: { session: SessionOut }) {
  const [expanded, setExpanded] = useState(false);
  const tabs = session.block_log.filter(e => e.type === 'tab');
  const apps = session.block_log.filter(e => e.type === 'app');

  const tabCounts: Record<string, number> = {};
  const appCounts: Record<string, number> = {};
  tabs.forEach(e => { tabCounts[e.name] = (tabCounts[e.name] ?? 0) + 1; });
  apps.forEach(e => { appCounts[e.name] = (appCounts[e.name] ?? 0) + 1; });

  return (
    <TouchableOpacity
      style={rowStyles.card}
      onPress={() => setExpanded(e => !e)}
      activeOpacity={0.85}
    >
      <View style={rowStyles.top}>
        <Text style={rowStyles.goal} numberOfLines={1}>{session.goal}</Text>
        <Text style={rowStyles.date}>{fmtDate(session.started_at)}</Text>
      </View>
      <View style={rowStyles.pills}>
        {[
          ['⏱', fmtDur(session.duration_s)],
          ['⊘', `${session.blocked_count} blocked`],
          ['◈', session.profile_name],
        ].map(([icon, val]) => (
          <View key={val} style={rowStyles.pill}>
            <Text style={rowStyles.pillText}>{icon}  {val}</Text>
          </View>
        ))}
      </View>
      {expanded && session.block_log.length > 0 && (
        <View style={rowStyles.detail}>
          {Object.keys(tabCounts).length > 0 && (
            <View style={rowStyles.detailCol}>
              <Text style={[rowStyles.detailTitle, { color: Colors.red }]}>Sites blocked</Text>
              {Object.entries(tabCounts).map(([name, count]) => (
                <View key={name} style={rowStyles.detailRow}>
                  <Text style={rowStyles.detailName}>{name}</Text>
                  <View style={rowStyles.countBadge}>
                    <Text style={[rowStyles.countText, { color: Colors.red }]}>×{count}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
          {Object.keys(appCounts).length > 0 && (
            <View style={rowStyles.detailCol}>
              <Text style={[rowStyles.detailTitle, { color: Colors.amber }]}>Apps closed</Text>
              {Object.entries(appCounts).map(([name, count]) => (
                <View key={name} style={rowStyles.detailRow}>
                  <Text style={rowStyles.detailName}>{name}</Text>
                  <View style={[rowStyles.countBadge, { backgroundColor: '#1e1a00', borderColor: '#3a3000' }]}>
                    <Text style={[rowStyles.countText, { color: Colors.amber }]}>×{count}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

const rowStyles = StyleSheet.create({
  card: {
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    padding:         Spacing.md,
    gap:             8,
  },
  top: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'flex-start',
    gap:            8,
  },
  goal: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
    flex:       1,
  },
  date: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },
  pills: {
    flexDirection: 'row',
    gap:           6,
    flexWrap:      'wrap',
  },
  pill: {
    backgroundColor: Colors.bgRaised,
    borderRadius:    Radius.sm,
    paddingHorizontal: 8,
    paddingVertical:   3,
  },
  pillText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textSec,
  },
  detail: {
    backgroundColor: Colors.bgRaised,
    borderRadius:    Radius.sm,
    padding:         Spacing.sm,
    flexDirection:   'row',
    gap:             Spacing.md,
  },
  detailCol: { flex: 1, gap: 4 },
  detailTitle: {
    fontFamily:   Fonts.mono,
    fontSize:     FontSizes.xs,
    marginBottom: 2,
  },
  detailRow: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'center',
  },
  detailName: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
    color:      Colors.textPri,
    flex:       1,
  },
  countBadge: {
    backgroundColor: '#2a1018',
    borderColor:     '#3a1820',
    borderWidth:     1,
    borderRadius:    Radius.sm,
    paddingHorizontal: 6,
    paddingVertical:   2,
  },
  countText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
  },
});

// ── Main component ────────────────────────────────────────────────────────────
export default function HistoryScreen() {
  const [sessions,    setSessions]   = useState<SessionOut[]>([]);
  const [isLoading,   setIsLoading]  = useState(true);
  const [refreshing,  setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const data = await getHistory();
    if (data) setSessions(data);
    setIsLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  // ── Aggregate stats ──────────────────────────────────────────────────────
  const totalS     = sessions.reduce((a, s) => a + s.duration_s, 0);
  const totalB     = sessions.reduce((a, s) => a + s.blocked_count, 0);
  const avgS       = sessions.length ? Math.floor(totalS / sessions.length) : 0;
  const allLogs    = sessions.flatMap(s => s.block_log);
  const tabCounts: Record<string, number> = {};
  const appCounts: Record<string, number> = {};
  allLogs.forEach(e => {
    if (e.type === 'tab') tabCounts[e.name] = (tabCounts[e.name] ?? 0) + 1;
    else                  appCounts[e.name] = (appCounts[e.name] ?? 0) + 1;
  });
  const topTabs = Object.entries(tabCounts).sort((a, b) => b[1] - a[1]);
  const topApps = Object.entries(appCounts).sort((a, b) => b[1] - a[1]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Session History</Text>
      </View>

      <Divider />

      {isLoading ? (
        <View style={styles.loader}>
          <ActivityIndicator color={Colors.accent} />
        </View>
      ) : (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={Colors.accent}
            />
          }
        >
          {sessions.length === 0 ? (
            <Text style={styles.empty}>No sessions recorded yet.</Text>
          ) : (
            <>
              {/* Stat cards */}
              <View style={styles.statsRow}>
                {[
                  ['Sessions',    String(sessions.length)],
                  ['Total focus', fmtDur(totalS)],
                  ['Avg session', fmtDur(avgS)],
                  ['Blocked',     String(totalB)],
                ].map(([label, val]) => (
                  <View key={label} style={styles.statCard}>
                    <Text style={styles.statVal}>{val}</Text>
                    <Text style={styles.statLabel}>{label}</Text>
                  </View>
                ))}
              </View>

              {/* Most-blocked charts */}
              {(topTabs.length > 0 || topApps.length > 0) && (
                <Card style={styles.chartsCard}>
                  <View style={styles.chartsRow}>
                    <MiniChart title="🔴  Sites" color={Colors.red}   items={topTabs} />
                    {topApps.length > 0 && <View style={styles.chartDivider} />}
                    <MiniChart title="🟡  Apps"  color={Colors.amber} items={topApps} />
                  </View>
                </Card>
              )}

              <Divider style={styles.sectionDiv} />
              <Text style={styles.sectionLabel}>SESSIONS</Text>

              {sessions.map(s => (
                <SessionRow key={s.id} session={s} />
              ))}
            </>
          )}
        </ScrollView>
      )}
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
    paddingBottom:     Spacing.md,
  },
  title: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.xl,
    color:      Colors.textPri,
  },
  loader: {
    flex:           1,
    justifyContent: 'center',
    alignItems:     'center',
  },
  scroll:  { flex: 1 },
  content: {
    padding: Spacing.lg,
    gap:     Spacing.sm,
  },
  empty: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textMut,
    textAlign:  'center',
    marginTop:  Spacing.xl,
  },

  statsRow: {
    flexDirection: 'row',
    gap:           6,
    marginBottom:  Spacing.sm,
  },
  statCard: {
    flex:            1,
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    padding:         Spacing.sm,
    alignItems:      'center',
  },
  statVal: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
    marginBottom: 2,
  },
  statLabel: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
  },

  chartsCard: { marginBottom: Spacing.sm },
  chartsRow:  { flexDirection: 'row', gap: Spacing.md },
  chartDivider: {
    width:           1,
    backgroundColor: Colors.border,
  },

  sectionDiv:   { marginVertical: Spacing.sm },
  sectionLabel: {
    fontFamily:    Fonts.mono,
    fontSize:      FontSizes.xs,
    color:         Colors.textMut,
    letterSpacing: 0.5,
    marginBottom:  Spacing.sm,
  },
});
