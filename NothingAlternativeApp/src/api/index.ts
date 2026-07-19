// Nothing Alternative — API client
// Mirrors the backend endpoints in main.py / auth.py / sessions.py / profiles.py / billing.py

import * as SecureStore from 'expo-secure-store';

const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? ' ';
const TOKEN_KEY = 'na_jwt';

// ── Token helpers ─────────────────────────────────────────────────────────────
export async function getStoredToken(): Promise<string | null> {
  try { return await SecureStore.getItemAsync(TOKEN_KEY); }
  catch { return null; }
}

export async function storeToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getStoredToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ── Generic fetch helpers ─────────────────────────────────────────────────────
function xhrRequest<T>(method: string, url: string, headers: Record<string, string>, body?: object): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.onload = () => {
      console.log(`[XHR] ${method} ${url} → ${xhr.status}`);  // add
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText}`));
      }
    };
    xhr.setRequestHeader('Connection', 'close');
    xhr.onerror = (e) => {
      console.log(`[XHR] ${method} ${url} → onerror`, JSON.stringify(e));  // add
      reject(new Error('Network request failed'));
    };
    xhr.onerror = (e) => {
      console.log(`[XHR] ${method} ${url} → onerror, headers sent:`, JSON.stringify(headers));
      reject(new Error('Network request failed'));
    };
    xhr.onerror = (e) => {
      console.log(`[XHR] ${method} ${url} → onerror, status=${xhr.status}, readyState=${xhr.readyState}`);
      reject(new Error('Network request failed'));
    };
    xhr.send(body ? JSON.stringify(body) : undefined);
  });
}

async function apiGet<T>(path: string, retries = 2): Promise<T | null> {
  try {
    const headers = await authHeaders();
    return await xhrRequest<T>('GET', `${API_BASE}${path}`, headers);
  } catch (e: any) {
    console.error(`[API] GET ${path} error:`, e.message);
    if (retries > 0) {
      await new Promise(res => setTimeout(res, 2000));
      return apiGet(path, retries - 1);
    }
    return null;
  }
}

async function apiPost<T>(path: string, body: object, retries = 2): Promise<T | null> {
  try {
    const headers = await authHeaders();
    return await xhrRequest<T>('POST', `${API_BASE}${path}`, headers, body);
  } catch (e: any) {
    console.error(`[API] POST ${path} error:`, e.message);
    if (retries > 0) {
      await new Promise(res => setTimeout(res, 2000));
      return apiPost(path, body, retries - 1);
    }
    return null;
  }
}

async function apiPut<T>(path: string, body: object, retries = 2): Promise<T | null> {
  try {
    const headers = await authHeaders();
    return await xhrRequest<T>('PUT', `${API_BASE}${path}`, headers, body);
  } catch (e: any) {
    console.error(`[API] PUT ${path} error:`, e.message);
    if (retries > 0) {
      await new Promise(res => setTimeout(res, 2000));
      return apiPut(path, body, retries - 1);
    }
    return null;
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  token_type:   string;
  user_id:      string;
  email:        string;
  display_name: string | null;
}

export interface Profile {
  id:              string;
  name:            string;
  allowed_apps:    string[];
  banned_keywords: string[];
  is_active:       boolean;
  updated_at:      string;
}

export interface SessionStatus {
  active:       boolean;
  blocked:      string[];
  allowed_apps: string[];
  goal:         string | null;
  started_at:   string | null;
  started_by:   string | null;
  subscription_status?: string;
  is_premium?:          boolean;
  trial_ends_at?:       string | null;
}

export interface StartSessionPayload {
  goal:            string;
  profile_name:    string;
  allowed_apps:    string[];
  banned_keywords: string[];
  device_id?:      string;
}

export interface SessionOut {
  id:            string;
  goal:          string;
  profile_name:  string;
  started_at:    string;
  ended_at:      string | null;
  duration_s:    number;
  blocked_count: number;
  block_log:     { type: string; name: string; ts: string }[];
  device_id:     string | null;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function authGoogle(idToken: string): Promise<TokenResponse | null> {
  return apiPost<TokenResponse>('/auth/google', { id_token: idToken });
}

export async function authApple(
  idToken: string,
  email: string | null,
  displayName: string | null,
): Promise<TokenResponse | null> {
  return apiPost<TokenResponse>('/auth/apple', {
    id_token:     idToken,
    email:        email ?? undefined,
    display_name: displayName ?? undefined,
  });
}

export async function getMe(): Promise<TokenResponse | null> {
  return apiGet<TokenResponse>('/auth/me');
}

// ── Profiles ──────────────────────────────────────────────────────────────────
export async function getProfiles(): Promise<Profile[] | null> {
  return apiGet<Profile[]>('/profiles/');
}

export async function syncProfiles(
  profiles: Omit<Profile, 'id' | 'updated_at'>[],
  activeProfile: string,
): Promise<Profile[] | null> {
  return apiPut<Profile[]>('/profiles/', { profiles, active_profile: activeProfile });
}

import { Platform } from 'react-native';

export async function getDeviceId(): Promise<string> {
  try {
    const { default: DeviceInfo } = await import('expo-device');
    return `${Platform.OS}-${DeviceInfo.modelName ?? 'device'}`;
  } catch {
    return `${Platform.OS}-device`;
  }
}

// ── Sessions ──────────────────────────────────────────────────────────────────
export async function getSessionStatus(): Promise<SessionStatus | null> {
  return apiGet<SessionStatus>('/sessions/status');
}

export async function startSession(body: {
  goal:            string;
  profile_name:    string;
  allowed_apps:    string[];
  banned_keywords: string[];
  device_id?:      string;
}): Promise<SessionStatus | null> {
  return apiPost<SessionStatus>('/sessions/start', body);
}

export async function stopSession(body: {
  duration_s:    number;
  blocked_count: number;
  block_log:     { type: string; name: string; ts: string }[];
  device_id?:    string;
  goal?:         string;
  profile_name?: string;
}): Promise<SessionOut | null> {
  return apiPost<SessionOut>('/sessions/stop', body);
}

export async function getSessionHistory(
  limit = 120,
  offset = 0,
): Promise<SessionOut[] | null> {
  return apiGet<SessionOut[]>(`/sessions/history?limit=${limit}&offset=${offset}`);
}

// ── Billing ───────────────────────────────────────────────────────────────────
export async function createCheckout(
  plan: 'monthly' | 'yearly' | 'lifetime',
): Promise<{ checkout_url: string } | null> {
  return apiPost('/billing/checkout', { plan });
}

export async function getBillingPortal(): Promise<{ portal_url: string } | null> {
  return apiGet('/billing/portal');
}

// ── Aliases for AuthContext compatibility ─────────────────────────────────────
export const getToken  = getStoredToken;
export const saveToken = storeToken;
export const authMe    = getMe;

// Aliases for screen compatibility
export const getHistory = getSessionHistory;

export async function getCheckoutUrl(
  plan: 'monthly' | 'yearly' | 'lifetime',
): Promise<string | null> {
  const res = await createCheckout(plan);
  return res?.checkout_url ?? null;
}