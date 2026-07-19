/**
 * SessionContext
 *
 * Single source of truth for session state across the app.
 *
 * Polling behaviour (matches desktop exactly):
 *   - During a session: poll /sessions/status every 2 seconds
 *   - Idle:             poll every 10 seconds (subscription status)
 *
 * Cross-device sync: if another device starts a session, this context
 * reflects active: true within 2 seconds and updates the UI automatically.
 * The phone does NOT re-post /sessions/start in this case — it just joins
 * the existing session by reading state from /sessions/status.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  ReactNode,
} from 'react';
import {
  getSessionStatus,
  startSession,
  stopSession,
  SessionStatus,
  StartSessionPayload,
  getDeviceId,
} from '../api';

export interface BlockLogEntry {
  type: 'tab' | 'app';
  name: string;
  ts:   string;
}

interface SessionState {
  // Current session
  isActive:       boolean;
  goal:           string | null;
  startedAt:      string | null;
  startedBy:      string | null;
  blockedSites:   string[];
  allowedApps:    string[];
  elapsedSeconds: number;
  blockedCount:   number;
  blockLog:       BlockLogEntry[];

  // Subscription
  subStatus:   string;
  trialEndsAt: string | null;
  isPremium:   boolean;

  // Actions
  startSession:  (payload: Omit<StartSessionPayload, 'device_id'>) => Promise<boolean>;
  stopSession:   () => Promise<void>;
  addBlockEntry: (entry: BlockLogEntry) => void;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [isActive,       setIsActive]       = useState(false);
  const [goal,           setGoal]           = useState<string | null>(null);
  const [startedAt,      setStartedAt]      = useState<string | null>(null);
  const [startedBy,      setStartedBy]      = useState<string | null>(null);
  const [blockedSites,   setBlockedSites]   = useState<string[]>([]);
  const [allowedApps,    setAllowedApps]    = useState<string[]>([]);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [blockedCount,   setBlockedCount]   = useState(0);
  const [blockLog,       setBlockLog]       = useState<BlockLogEntry[]>([]);
  const [subStatus,      setSubStatus]      = useState('free');
  const [trialEndsAt,    setTrialEndsAt]    = useState<string | null>(null);
  const [isPremium,      setIsPremium]      = useState(false);

  const pollRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tickRef    = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Tracks the server-side session state so we can detect transitions
  const sessionRef = useRef({
    isActive:  false,
    startedAt: '',   // ISO string from the server
  });

  // ── Elapsed time recalculation from server's started_at ─────────────────
  // Always derive elapsed from the authoritative started_at timestamp so it
  // stays correct even when the session was started on another device.
  const calcElapsed = (startedAtIso: string): number => {
    try {
      const started = new Date(startedAtIso).getTime();
      const now     = Date.now();
      const diff    = Math.floor((now - started) / 1000);
      // Guard against clock skew / bad timestamps
      return diff < 0 ? 0 : diff;
    } catch {
      return 0;
    }
  };

  // ── Apply status from server ─────────────────────────────────────────────
  const applyStatus = useCallback((status: SessionStatus) => {
    console.log('[STATUS]', JSON.stringify(status));

    const wasActive  = sessionRef.current.isActive;
    const nowActive  = status.active;
    const serverStart = status.started_at ?? '';

    setIsActive(nowActive);
    setBlockedSites(status.blocked);
    setAllowedApps(status.allowed_apps);
    setGoal(status.goal ?? null);
    setStartedAt(serverStart || null);
    setStartedBy(status.started_by ?? null);

    if (status.subscription_status) setSubStatus(status.subscription_status);
    if (status.trial_ends_at  !== undefined) setTrialEndsAt(status.trial_ends_at ?? null);
    if (status.is_premium     !== undefined) setIsPremium(status.is_premium);

    if (nowActive) {
      if (!wasActive && serverStart) {
        // Session just became active (local start or remote start detected)
        // Seed elapsed from the server's started_at so it's always accurate.
        setElapsedSeconds(calcElapsed(serverStart));
      }
      // Keep sessionRef up to date
      sessionRef.current = { isActive: true, startedAt: serverStart };
    } else {
      if (wasActive) {
        // Session just ended
        setElapsedSeconds(0);
        setBlockedCount(0);
        setBlockLog([]);
      }
      sessionRef.current = { isActive: false, startedAt: '' };
    }
  }, []);

  // ── Polling loop ──────────────────────────────────────────────────────────
  const scheduleNextPoll = useCallback((active: boolean) => {
    if (pollRef.current) clearTimeout(pollRef.current);
    pollRef.current = setTimeout(async () => {
      const status = await getSessionStatus();
      if (status) applyStatus(status);
      scheduleNextPoll(sessionRef.current.isActive);
    }, active ? 2000 : 10000);
  }, [applyStatus]);

  // Initial fetch + start poll
  useEffect(() => {
    (async () => {
      const status = await getSessionStatus();
      if (status) applyStatus(status);
      scheduleNextPoll(status?.active ?? false);
    })();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
      if (tickRef.current) clearTimeout(tickRef.current);
    };
  }, [applyStatus, scheduleNextPoll]);

  // ── Elapsed time ticker ───────────────────────────────────────────────────
  // Ticks every second while a session is active.
  // The starting value is already seeded correctly by applyStatus above.
  useEffect(() => {
    if (tickRef.current) clearTimeout(tickRef.current);
    if (!isActive) return;

    const tick = () => {
      setElapsedSeconds(s => s + 1);
      tickRef.current = setTimeout(tick, 1000);
    };
    tickRef.current = setTimeout(tick, 1000);
    return () => { if (tickRef.current) clearTimeout(tickRef.current); };
  }, [isActive]);

  // ── Start session ─────────────────────────────────────────────────────────
  // Only posts to the backend if there is no session already active.
  // If another device already started one, we just join it locally.
  const isStartingRef = useRef(false);

  const handleStartSession = useCallback(
    async (payload: Omit<StartSessionPayload, 'device_id'>): Promise<boolean> => {
      if (isStartingRef.current) return false;

      // If a session is already active (started by another device and detected
      // via polling), don't POST /sessions/start — just return true so the UI
      // transitions to the active state. The polling loop already called
      // applyStatus which set isActive = true.
      if (sessionRef.current.isActive) {
        console.log('[SESSION] Session already active (remote), joining locally');
        return true;
      }

      isStartingRef.current = true;
      try {
        const deviceId = await getDeviceId();
        const result   = await startSession({ ...payload, device_id: deviceId });
        if (!result) return false;
        applyStatus(result);
        scheduleNextPoll(true);
        return true;
      } catch (e: any) {
        // 409 = another device beat us to it — fetch current status and join
        if (e?.message?.includes('409')) {
          console.log('[SESSION] 409 on start — fetching current status to join');
          const status = await getSessionStatus();
          if (status?.active) {
            applyStatus(status);
            scheduleNextPoll(true);
            return true;
          }
        }
        return false;
      } finally {
        isStartingRef.current = false;
      }
    },
    [applyStatus, scheduleNextPoll]
  );

  // ── Stop session ──────────────────────────────────────────────────────────
  const handleStopSession = useCallback(async () => {
    // Use the live elapsed from state (ticked every second) not a snapshot
    // taken at mount time, which is what caused elapsed: -25184.
    const snap_elapsed   = elapsedSeconds;
    const snap_blocked   = blockedCount;
    const snap_blockLog  = [...blockLog];
    const snap_goal      = goal ?? '';

    console.log('[SESSION] stopSession called, elapsed:', snap_elapsed);

    const deviceId = await getDeviceId();
    await stopSession({
      duration_s:    snap_elapsed,
      blocked_count: snap_blocked,
      block_log:     snap_blockLog,
      device_id:     deviceId,
      goal:          snap_goal,
      profile_name:  'Default',
    });

    // Optimistically clear local state; the next poll will confirm
    setIsActive(false);
    setElapsedSeconds(0);
    setBlockedCount(0);
    setBlockLog([]);
    sessionRef.current = { isActive: false, startedAt: '' };
    scheduleNextPoll(false);
  }, [elapsedSeconds, blockedCount, blockLog, goal, scheduleNextPoll]);

  const addBlockEntry = useCallback((entry: BlockLogEntry) => {
    setBlockLog(prev => [...prev, entry]);
    setBlockedCount(c => c + 1);
  }, []);

  return (
    <SessionContext.Provider value={{
      isActive,
      goal,
      startedAt,
      startedBy,
      blockedSites,
      allowedApps,
      elapsedSeconds,
      blockedCount,
      blockLog,
      subStatus,
      trialEndsAt,
      isPremium,
      startSession: handleStartSession,
      stopSession:  handleStopSession,
      addBlockEntry,
    }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside SessionProvider');
  return ctx;
}
