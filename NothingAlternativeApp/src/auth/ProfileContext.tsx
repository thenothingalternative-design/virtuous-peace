/**
 * ProfileContext
 *
 * Manages focus profiles locally and syncs to the backend.
 * On mount: GET /profiles/ — backend is authoritative for contents,
 *           local state is authoritative for which profile is active.
 * Any mutation immediately PUTs the full list (last-write-wins).
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  ReactNode,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getProfiles, syncProfiles, Profile } from '../api';

const PROFILES_KEY   = 'na_profiles';
const ACTIVE_KEY     = 'na_active_profile';

const DEFAULT_PROFILE: Omit<Profile, 'id' | 'updated_at'> = {
  name:            'Default',
  allowed_apps:    [ 'browsers'/*'chrome', 'firefox', 'brave', 'opera', 'samsung', 'browser', 'edge', 'duckduckgo', 'vivaldi', 'yandex', 'tor', 'maxthon'*/],  
  banned_keywords: ['youtube', 'facebook', 'instagram', 'twitter',
                    'x.com', 'reddit', 'tiktok', 'netflix'],
  is_active:       true,
};

interface ProfileState {
  profiles:       Profile[];
  activeProfile:  Profile | null;
  isLoading:      boolean;
  setActiveProfile: (name: string) => void;
  createProfile:    (name: string) => void;
  deleteProfile:    (name: string) => void;
  addAllowedApp:    (appHint: string) => void;
  removeAllowedApp: (appHint: string) => void;
  addBlockedKeyword:    (kw: string) => void;
  removeBlockedKeyword: (kw: string) => void;
}

const ProfileContext = createContext<ProfileState | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profiles,      setProfiles]      = useState<Profile[]>([]);
  const [activeProfile, setActiveProfileState] = useState<Profile | null>(null);
  const [isLoading,     setIsLoading]     = useState(true);

  // ── Load from local storage then sync from backend ───────────────────────
  useEffect(() => {
    (async () => {
      try {
        // Load local state first (instant)
        const [localRaw, localActive] = await Promise.all([
          AsyncStorage.getItem(PROFILES_KEY),
          AsyncStorage.getItem(ACTIVE_KEY),
        ]);
        let localProfiles: Profile[] = localRaw ? JSON.parse(localRaw) : [];
        const activeName = localActive ?? 'Default';

        if (localProfiles.length === 0) {
          localProfiles = [{ ...DEFAULT_PROFILE, id: 'default', updated_at: '' }];
        }
        setProfiles(localProfiles);
        setActiveProfileState(localProfiles.find(p => p.name === activeName) ?? localProfiles[0]);

        // Fetch from backend (authoritative for contents)
        const remote = await getProfiles();
        if (remote && remote.length > 0) {
          const mergedActive = remote.find(p => p.name === activeName) ?? remote[0];
          setProfiles(remote);
          setActiveProfileState(mergedActive);
          await AsyncStorage.setItem(PROFILES_KEY, JSON.stringify(remote));
        }
      } catch (e) {
        console.warn('[PROFILES] load error:', e);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  // ── Persist + sync helper ─────────────────────────────────────────────────
  const saveAndSync = useCallback(async (
    nextProfiles: Profile[],
    activeName: string
  ) => {
    await AsyncStorage.setItem(PROFILES_KEY, JSON.stringify(nextProfiles));
    await AsyncStorage.setItem(ACTIVE_KEY, activeName);
    // Non-blocking backend sync
    syncProfiles(
      nextProfiles.map(p => ({
        name:            p.name,
        allowed_apps:    p.allowed_apps,
        banned_keywords: p.banned_keywords,
        is_active:       p.name === activeName,
      })),
      activeName,
    ).catch(e => console.warn('[PROFILES] sync error:', e));
  }, []);

  // ── Active profile setter ─────────────────────────────────────────────────
  const setActiveProfile = useCallback((name: string) => {
    setProfiles(prev => {
      const next = prev.map(p => ({ ...p, is_active: p.name === name }));
      const active = next.find(p => p.name === name) ?? next[0];
      setActiveProfileState(active);
      saveAndSync(next, name);
      return next;
    });
  }, [saveAndSync]);

  // ── Create / delete profile ───────────────────────────────────────────────
  const createProfile = useCallback((name: string) => {
    if (!name.trim()) return;
    setProfiles(prev => {
      if (prev.find(p => p.name === name)) return prev;
      const newProfile: Profile = {
        id:              Math.random().toString(36).slice(2),
        name,
        allowed_apps:    [],
        banned_keywords: [...DEFAULT_PROFILE.banned_keywords],
        is_active:       false,
        updated_at:      new Date().toISOString(),
      };
      const next = [...prev, newProfile];
      const activeName = prev.find(p => p.is_active)?.name ?? 'Default';
      saveAndSync(next, activeName);
      return next;
    });
  }, [saveAndSync]);

  const deleteProfile = useCallback((name: string) => {
    if (name === 'Default') return;
    setProfiles(prev => {
      const next = prev.filter(p => p.name !== name);
      const currentActive = prev.find(p => p.is_active)?.name ?? 'Default';
      const activeName = currentActive === name ? (next[0]?.name ?? 'Default') : currentActive;
      const active = next.find(p => p.name === activeName) ?? next[0];
      setActiveProfileState(active ?? null);
      saveAndSync(next, activeName);
      return next;
    });
  }, [saveAndSync]);

  // ── Mutate active profile's app/keyword lists ─────────────────────────────
  const mutateActive = useCallback((
    fn: (p: Profile) => Profile
  ) => {
    setProfiles(prev => {
      const activeName = prev.find(p => p.is_active)?.name ?? prev[0]?.name ?? 'Default';
      const next = prev.map(p => p.is_active ? fn(p) : p);
      const newActive = next.find(p => p.is_active) ?? next[0];
      setActiveProfileState(newActive ?? null);
      saveAndSync(next, activeName);
      return next;
    });
  }, [saveAndSync]);

  const addAllowedApp = useCallback((hint: string) => {
    mutateActive(p => ({
      ...p,
      allowed_apps: p.allowed_apps.includes(hint)
        ? p.allowed_apps
        : [...p.allowed_apps, hint],
    }));
  }, [mutateActive]);

  const removeAllowedApp = useCallback((hint: string) => {
    mutateActive(p => ({
      ...p,
      allowed_apps: p.allowed_apps.filter(a => a !== hint),
    }));
  }, [mutateActive]);

  const addBlockedKeyword = useCallback((kw: string) => {
    const clean = kw
      .toLowerCase()
      .replace(/https?:\/\//, '')
      .replace(/www\./, '')
      .split('/')[0]
      .trim();
    if (!clean) return;
    mutateActive(p => ({
      ...p,
      banned_keywords: p.banned_keywords.includes(clean)
        ? p.banned_keywords
        : [...p.banned_keywords, clean],
    }));
  }, [mutateActive]);

  const removeBlockedKeyword = useCallback((kw: string) => {
    mutateActive(p => ({
      ...p,
      banned_keywords: p.banned_keywords.filter(k => k !== kw),
    }));
  }, [mutateActive]);

  return (
    <ProfileContext.Provider value={{
      profiles,
      activeProfile,
      isLoading,
      setActiveProfile,
      createProfile,
      deleteProfile,
      addAllowedApp,
      removeAllowedApp,
      addBlockedKeyword,
      removeBlockedKeyword,
    }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfiles(): ProfileState {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfiles must be used inside ProfileProvider');
  return ctx;
}
