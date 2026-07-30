// services/purchases.ts
// RevenueCat wrapper — Android IAP (iOS will use the same code automatically)

import Purchases, {
  LOG_LEVEL,
  type PurchasesOffering,
  type CustomerInfo,
} from 'react-native-purchases';
import { Platform } from 'react-native';

const RC_ANDROID_KEY = process.env.EXPO_PUBLIC_RC_ANDROID_KEY ?? '';
const RC_IOS_KEY     = process.env.EXPO_PUBLIC_RC_IOS_KEY ?? '';

export async function initRevenueCat(userId: string): Promise<void> {
  const apiKey = Platform.OS === 'ios' ? RC_IOS_KEY : RC_ANDROID_KEY;
  if (!apiKey) return;

  Purchases.setLogLevel(LOG_LEVEL.WARN);
  await Purchases.configure({ apiKey });

  // Link RC to your backend user ID so webhook events map back to the right user
  await Purchases.logIn(userId);
}

export async function getOfferings(): Promise<PurchasesOffering | null> {
  try {
    const offerings = await Purchases.getOfferings();
    return offerings.current ?? null;
  } catch (e) {
    console.error('[RC] getOfferings error:', e);
    return null;
  }
}

export async function purchasePackage(
  pkg: import('react-native-purchases').PurchasesPackage,
): Promise<CustomerInfo | null> {
  try {
    const { customerInfo } = await Purchases.purchasePackage(pkg);
    return customerInfo;
  } catch (e: any) {
    if (!e.userCancelled) console.error('[RC] purchasePackage error:', e);
    return null;
  }
}

export async function restorePurchases(): Promise<CustomerInfo | null> {
  try {
    return await Purchases.restorePurchases();
  } catch (e) {
    console.error('[RC] restorePurchases error:', e);
    return null;
  }
}

export async function getCustomerInfo(): Promise<CustomerInfo | null> {
  try {
    return await Purchases.getCustomerInfo();
  } catch (e) {
    console.error('[RC] getCustomerInfo error:', e);
    return null;
  }
}

/** Returns true if the user has any active entitlement (use "premium" as your entitlement ID in RC dashboard) */
export function isEntitled(customerInfo: CustomerInfo): boolean {
  return typeof customerInfo.entitlements.active['premium'] !== 'undefined';
}