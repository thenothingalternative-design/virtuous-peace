/**
 * App.tsx — Nothing Alternative Mobile
 *
 * Provider tree:
 *   SafeAreaProvider
 *     AuthProvider        — JWT storage, sign-in/out
 *       ProfileProvider   — profile state + backend sync
 *         SessionProvider — session state + 2s polling
 *           RootNavigator — screens
 *           BlockingLayer — platform blocking + overlay
 */

import { Text, View } from 'react-native'; // 👈 Add this import at the top if needed
import React, { useEffect, useState } from 'react';
import { Platform, StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Font from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';


import { AuthProvider }    from './src/auth/AuthContext';
import { ProfileProvider } from './src/auth/ProfileContext';
import { SessionProvider, useSession } from './src/auth/SessionContext';
import RootNavigator from './src/navigation';
import BlockingOverlay from './src/components/BlockingOverlay';
import { useBlockingSetup } from './src/utils/useBlockingSetup';
import { useAndroidForegroundService } from './src/utils/useAndroidForegroundService';

SplashScreen.preventAutoHideAsync();

// ── Blocking layer — rendered inside SessionProvider ─────────────────────────
function BlockingLayer() {
  const session = useSession();
  const {
    blockedAppOverlay,
    blockingStatus,
    clearOverlay,
    requestPermission,
  } = useBlockingSetup();

  // Start / stop Android foreground service with session
  useAndroidForegroundService();

  return (
    <>
      {Platform.OS === 'android' && (
        <BlockingOverlay
          visible={blockedAppOverlay !== null}
          blockedApp={blockedAppOverlay ?? ''}
          onDismiss={clearOverlay}
        />
      )}
    </>
  );
}

// ── Font loading + root ───────────────────────────────────────────────────────
export default function App() {
  //const [fontsLoaded, setFontsLoaded] = useState(false);
  const [fontsLoaded, setFontsLoaded] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        
        await Font.loadAsync({
          'DMSans':      require('./assets/fonts/DMSans-Regular.ttf'),
          'DMSans-Bold': require('./assets/fonts/DMSans-Bold.ttf'),
          'DMMono':      require('./assets/fonts/DMMono-Regular.ttf'),
        }); 
      } catch (e) {
        console.warn('[FONTS] load error — using system fonts as fallback:', e);
      } finally {
        //setFontsLoaded(true);
        await SplashScreen.hideAsync();
      }
    })();
  }, []);


  /*if (!fontsLoaded) {
    return null;
  }*/

  if (!fontsLoaded) return (
  <SafeAreaProvider>
    <AuthProvider>
      <ProfileProvider>
        <SessionProvider>
          <BlockingLayer />
        </SessionProvider>
      </ProfileProvider>
    </AuthProvider>
  </SafeAreaProvider> 
);

  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" backgroundColor="#0e0e0f" />
      <AuthProvider>
        <ProfileProvider>
          <SessionProvider>
            <RootNavigator />
            <BlockingLayer />
          </SessionProvider>
        </ProfileProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

  /*return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0e0e0f' }}>
      <Text style={{ color: 'white', fontSize: 20 }}>JS Thread is Alive!</Text>
    </View>
  );
}*/
