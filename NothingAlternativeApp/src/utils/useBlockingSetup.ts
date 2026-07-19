import { useEffect, useRef, useState, useCallback } from 'react';
import { Platform } from 'react-native';
import { useSession } from '../auth/SessionContext';
import {
  startBlockingLoop,
  hasUsageStatsPermission,
  openUsageStatsSettings,
} from './androidBlocking';
import {
  applyIOSBlocking,
  clearIOSBlocking,
  getScreenTimeAuthStatus,
} from './iosBlocking';
import { NativeEventEmitter, NativeModules } from 'react-native';

export type BlockingStatus =
  | 'idle'
  | 'permission_needed'
  | 'active_screentime'
  | 'active_focusfilter'
  | 'active_usagestats'
  | 'unavailable';

export interface BlockingSetupResult {
  blockingStatus:    BlockingStatus;
  blockedAppOverlay: string | null;
  clearOverlay:      () => void;
  requestPermission: () => void;
}

export function useBlockingSetup(): BlockingSetupResult {
  const session = useSession();

  const [blockingStatus,    setBlockingStatus]    = useState<BlockingStatus>('idle');
  const [blockedAppOverlay, setBlockedAppOverlay] = useState<string | null>(null);
  const stopLoopRef      = useRef<(() => void) | null>(null);
  const isBlockingActive = useRef(false); // ← replaces isFirstRender

  // Check permission on mount
  useEffect(() => {
    (async () => {
      if (Platform.OS === 'android') {
        const granted = await hasUsageStatsPermission();
        if (!granted) setBlockingStatus('permission_needed');
      } else if (Platform.OS === 'ios') {
        const status = await getScreenTimeAuthStatus();
        if (status === 'unavailable') setBlockingStatus('unavailable');
      }
    })();
  }, []);

    useEffect(() => {
      const emitter = new NativeEventEmitter();
      const sub = emitter.addListener('ShowBlockingOverlay', () => {
        setBlockedAppOverlay('blocked');
      });
      return () => sub.remove();
    }, []);
  

  // React to session state — NO first-render guard
  // This is intentional: sessions can become active on mount if another
  // device already started one and the poll picks it up immediately.
  useEffect(() => {
    if (session.isActive && !isBlockingActive.current) {
      isBlockingActive.current = true;
      handleSessionStart();
    } else if (!session.isActive && isBlockingActive.current) {
      isBlockingActive.current = false;
      handleSessionEnd();
    }
    return () => {
      if (!session.isActive) {
        stopLoopRef.current?.();
        stopLoopRef.current = null;
      }
    };
  }, [session.isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSessionStart = async () => {
    console.log('[BLOCKING] starting, blockedSites:', session.blockedSites, 'allowedApps:', session.allowedApps);
    if (Platform.OS === 'android') {
      const granted = await hasUsageStatsPermission();
      if (!granted) {
        setBlockingStatus('permission_needed');
        isBlockingActive.current = false;
        return;
      }
      stopLoopRef.current?.(); // clear any stale loop
      const stop = startBlockingLoop(
        session.blockedSites,
        session.allowedApps,
        (pkg) => setBlockedAppOverlay(pkg),
      );
      stopLoopRef.current = stop;
      setBlockingStatus('active_usagestats');
    } else if (Platform.OS === 'ios') {
      const method = await applyIOSBlocking(
        session.blockedSites,
        session.goal ?? 'Focus session',
      );
      setBlockingStatus(
        method === 'screentime' ? 'active_screentime' :
        method === 'focusfilter' ? 'active_focusfilter' :
        'unavailable'
      );
    }
  };

  const handleSessionEnd = async () => {
    stopLoopRef.current?.();
    stopLoopRef.current = null;
    setBlockedAppOverlay(null);
    if (Platform.OS === 'ios') await clearIOSBlocking();
    setBlockingStatus('idle');
  };

  const requestPermission = useCallback(() => {
    if (Platform.OS === 'android') openUsageStatsSettings();
  }, []);

  const clearOverlay = useCallback(() => setBlockedAppOverlay(null), []);

  return { blockingStatus, blockedAppOverlay, clearOverlay, requestPermission };
}