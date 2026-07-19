# Nothing Alternative — Mobile App

React Native (Expo bare workflow) | iOS + Android

## Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | React Native (Expo bare) | Single codebase, full native access |
| Navigation | React Navigation v6 | Stack + bottom tabs |
| Auth storage | expo-secure-store | iOS Keychain / Android Keystore |
| Local data | @react-native-async-storage | Profiles, config |
| Fonts | DM Sans + DM Mono | Matches desktop exactly |
| Android blocking | UsageStatsManager (native module) | Policy-safe, no AccessibilityService |
| iOS blocking | FamilyControls + Screen Time API | Requires entitlement (apply first) |

---

## Project structure

```
src/
  api/           — All backend calls (/auth, /profiles, /sessions, /billing)
  auth/          — AuthContext, SessionContext, ProfileContext
  components/    — Chip, ChipRow, Card, SubscriptionBadge, BlockingOverlay, etc.
  navigation/    — Tab + stack navigator
  screens/
    Auth/        — SignInScreen
    Home/        — HomeScreen (main screen, session start/stop)
    Profiles/    — ProfilesScreen
    History/     — HistoryScreen
    Settings/    — SettingsScreen (apps + blocked sites tabs)
    Pricing/     — PricingScreen (3 Stripe plans)
  theme/         — Colors, Fonts, FontSizes, Radius, Spacing
  utils/
    androidBlocking.ts  — JS wrapper for UsageStatsManager polling
android/
  UsageStatsModule.kt   — Native Android module for foreground app detection
```

---

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Add fonts

Download DM Sans and DM Mono from Google Fonts and place TTF files in:
```
assets/fonts/
  DMSans-Regular.ttf
  DMSans-Bold.ttf
  DMMono-Regular.ttf
```

### 3. Configure Google Sign-In

In `src/screens/Auth/SignInScreen.tsx`, replace `webClientId` with your
actual OAuth 2.0 Web Client ID from Google Cloud Console.

Also set the same client ID in `android/app/google-services.json` (Android)
and `GoogleService-Info.plist` (iOS) — download these from Firebase Console
after registering the app.

### 4. Android: register the native module

In `android/app/src/main/java/com/nothingalternative/`:

1. Copy `UsageStatsModule.kt` into the package directory.
2. Create `UsageStatsPackage.kt`:

```kotlin
package com.nothingalternative

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager

class UsageStatsPackage : ReactPackage {
    override fun createNativeModules(ctx: ReactApplicationContext): List<NativeModule> =
        listOf(UsageStatsModule(ctx))
    override fun createViewManagers(ctx: ReactApplicationContext): List<ViewManager<*, *>> =
        emptyList()
}
```

3. Register it in `MainApplication.kt`:
```kotlin
override fun getPackages(): List<ReactPackage> =
    PackageList(this).packages.apply {
        add(UsageStatsPackage())
    }
```

4. Add to `AndroidManifest.xml` inside `<manifest>`:
```xml
<uses-permission
    android:name="android.permission.PACKAGE_USAGE_STATS"
    tools:ignore="ProtectedPermissions" />
```

### 5. iOS: Screen Time / FamilyControls

Apply for the `com.apple.developer.family-controls` entitlement at:
https://developer.apple.com/contact/request/family-controls-distribution

Once granted, the entitlement is already in `app.json`.
The FamilyControls integration (ManagedSettings + DeviceActivityMonitor)
will be built as a separate iOS app extension — see the iOS blocking guide.

### 6. Run

```bash
# iOS
npx expo run:ios

# Android
npx expo run:android
```

---

## Cross-device sync

The mobile app polls `/sessions/status`:
- **Every 2 seconds** while a session is active
- **Every 10 seconds** at idle (for subscription status)

If a session is started on the Mac or Windows app, the mobile app reflects
`active: true` within 2 seconds and shows the session state on the Home screen.
The reverse is also true — starting a session on mobile activates blocking
on all desktop devices immediately.

---

## Subscription states

| Status | Display | Colour | Tappable |
|---|---|---|---|
| `trialing` | Trial · Xd left | `#5555cc` → amber → red | ✓ → Pricing |
| `active` | Premium ✓ | green | ✗ |
| `lifetime` | Lifetime ✓ | green | ✗ |
| `expired` / `cancelled` / `free` | Upgrade → | amber | ✓ → Pricing |

Pricing: tapping a plan calls `POST /billing/checkout` → opens Stripe URL
in the system browser. No in-app purchase.

---

## Android blocking: UsageStats approach

1. On first session start, check `hasUsageStatsPermission()`.
2. If not granted, show a banner linking to Usage Access settings.
3. Once granted, `startBlockingLoop()` polls `getForegroundApp()` every second.
4. If the foreground app matches a banned keyword or isn't in the allowed list,
   `BlockingOverlay` is shown — a full-screen modal the user can only dismiss
   by stopping their session.
5. The hardware back button is intercepted while the overlay is visible.

**Play Store policy note:** UsageStatsManager for app detection is policy-safe
as long as the permission usage is clearly disclosed in the Play Store listing
and privacy policy. Do not use AccessibilityService for this purpose.
