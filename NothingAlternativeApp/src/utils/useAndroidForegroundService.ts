/**
 * useAndroidForegroundService
 *
 * Starts and stops the BlockingForegroundService in sync with session state.
 * This keeps the blocking loop alive when the screen is off.
 *
 * Only active on Android. No-op on iOS.
 */

import { useEffect, useRef } from 'react';
import { Platform, NativeModules } from 'react-native';
import { useSession } from '../auth/SessionContext';
import { getStoredToken } from '../api';

const { ForegroundServiceModule } = NativeModules as {
  ForegroundServiceModule?: {
    startService(goal: string, allowedApps: string[], blockedSites: string[], token: string): void;
    stopService(): void;
    prepareVpn(): Promise<boolean>;
  };
};

export function useAndroidForegroundService() {
  const session = useSession();
  const serviceRunning = useRef(false);

  useEffect(() => {
    if (Platform.OS !== 'android' || !ForegroundServiceModule) return;

    (async () => {
      if (session.isActive) {
        // Don't restart if already running
        if (serviceRunning.current) return;
        serviceRunning.current = true;

        const alreadyGranted = await ForegroundServiceModule.prepareVpn();
        if (!alreadyGranted) {
          serviceRunning.current = false;
          return;
        }

        // Wait up to 5 seconds for session data to populate from poll
        let data = session.latestSessionData.current;
        for (let i = 0; i < 10; i++) {
          if (data.goal) break;
          await new Promise(r => setTimeout(r, 500));
          data = session.latestSessionData.current;
        }

        if (!data.goal) {
          // Still no data after 5 seconds — abort
          console.warn('[FG_SERVICE] session data never populated, aborting');
          serviceRunning.current = false;
          return;
        }

        console.log('[FG_SERVICE] starting service with blockedSites:', data.blockedSites);
        const token = await getStoredToken() ?? '';
        console.log('[FG_SERVICE] goal:', data.goal, 'blockedSites:', data.blockedSites);
        ForegroundServiceModule.startService(
          data.goal,
          data.allowedApps,
          data.blockedSites,
          token,
        );
      } else {
        serviceRunning.current = false;
        console.log('[FG_SERVICE] calling stopService');
        ForegroundServiceModule.stopService();
      }
    })();
  }, [session.isActive]); // only re-fire when isActive changes, not on every poll
}