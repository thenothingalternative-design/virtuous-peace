/**
 * useAndroidForegroundService
 *
 * Starts and stops the BlockingForegroundService in sync with session state.
 * This keeps the blocking loop alive when the screen is off.
 *
 * Only active on Android. No-op on iOS.
 */

import { useEffect } from 'react';
import { Platform, NativeModules } from 'react-native';
import { useSession } from '../auth/SessionContext';

// react-native-foreground-service or direct Intent via a tiny native module
// We'll use a simple NativeModule bridge here.
const { ForegroundServiceModule } = NativeModules as {
  ForegroundServiceModule?: {
    startService(goal: string, allowedApps: string[]): void;
    stopService(): void;
  };
};

export function useAndroidForegroundService() {
  const session = useSession();

  useEffect(() => {
    if (Platform.OS !== 'android' || !ForegroundServiceModule) return;

    if (session.isActive) {
      ForegroundServiceModule.startService(
        session.goal ?? 'Focus session',
        session.allowedApps
      ); 
    } else {
      ForegroundServiceModule.stopService();
    }
  }, [session.isActive, session.goal, session.allowedApps]);
}
