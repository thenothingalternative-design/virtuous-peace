/**
 * AuthContext
 *
 * Provides token management, user info, and sign-in/sign-out to the whole app.
 * On mount: reads the saved JWT → validates it → shows sign-in if expired.
 * All platform-specific OAuth (Google / Apple) is handled by the calling screen;
 * this context only cares about the final JWT from the backend.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  ReactNode,
} from 'react';
import {
  getToken,
  saveToken,
  clearToken,
  authMe,
  TokenResponse,
} from '../api';

interface AuthState {
  isLoading:   boolean;
  isSignedIn:  boolean;
  userInfo:    TokenResponse | null;
  /** Call with the JWT response from /auth/google or /auth/apple */
  signIn:      (tokenData: TokenResponse) => Promise<void>;
  /** Clears token and returns to sign-in screen */
  signOut:     () => Promise<void>;
  /** Skip sign-in — offline mode */
  skipAuth:    () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoading,  setIsLoading]  = useState(true);
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [userInfo,   setUserInfo]   = useState<TokenResponse | null>(null);

  // On mount: try to restore session from secure storage
  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        if (!token) {
          setIsLoading(false);
          return;
        }
        // Validate the stored token in the background
        const me = await authMe();
        if (me) {
          setUserInfo({ ...me, access_token: token });
          setIsSignedIn(true);
        } else {
          // 401 or network failure — clear stale token, show sign-in
          await clearToken();
        }
      } catch {
        // Network unreachable — stay offline
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const signIn = useCallback(async (tokenData: TokenResponse) => {
    await saveToken(tokenData.access_token);
    setUserInfo(tokenData);
    setIsSignedIn(true);
  }, []);

  const signOut = useCallback(async () => {
    await clearToken();
    setUserInfo(null);
    setIsSignedIn(false);
  }, []);

  const skipAuth = useCallback(() => {
    setIsSignedIn(true); // offline mode — no token saved
  }, []);

  return (
    <AuthContext.Provider value={{
      isLoading,
      isSignedIn,
      userInfo,
      signIn,
      signOut,
      skipAuth,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
