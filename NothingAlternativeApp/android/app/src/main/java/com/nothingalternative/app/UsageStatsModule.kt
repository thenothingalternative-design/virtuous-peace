package com.nothingalternative.app

import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.provider.Settings
import android.app.AppOpsManager
import android.os.Process
import android.os.Build
import com.facebook.react.bridge.*
import java.util.SortedMap
import java.util.TreeMap

/**
 * UsageStatsModule
 *
 * Exposes to JS:
 *   - getForegroundApp()        → package name of current foreground app
 *   - hasUsageStatsPermission() → whether Usage Access is granted
 *   - openUsageStatsSettings()  → opens Usage Access settings screen
 *   - getInstalledApps()        → list of user-installed apps (replaces third-party package)
 */
class UsageStatsModule(private val reactContext: ReactApplicationContext)
    : ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "UsageStatsModule"

    // ── Permission ────────────────────────────────────────────────────────────

    @ReactMethod
    fun hasUsageStatsPermission(promise: Promise) {
        try {
            val appOps = reactContext.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
            val mode = appOps.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(),
                reactContext.packageName
            )
            promise.resolve(mode == AppOpsManager.MODE_ALLOWED)
        } catch (e: Exception) {
            promise.resolve(false)
        }
    }

    @ReactMethod
    fun openUsageStatsSettings() {
        try {
            val intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            reactContext.startActivity(intent)
        } catch (e: Exception) {
            try {
                val fallback = Intent(Settings.ACTION_SETTINGS).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                reactContext.startActivity(fallback)
            } catch (_: Exception) {}
        }
    }

    // ── Foreground app ────────────────────────────────────────────────────────

    @ReactMethod
    fun getForegroundApp(promise: Promise) {
        try {
            val usm = reactContext.getSystemService(Context.USAGE_STATS_SERVICE)
                    as UsageStatsManager

            val now    = System.currentTimeMillis()
            val window = 3_000L

            // Method 1: UsageEvents (accurate, API 21+)
            val events = usm.queryEvents(now - window, now)
            var lastPkg = ""
            var lastTs  = 0L

            val event = android.app.usage.UsageEvents.Event()
            while (events.hasNextEvent()) {
                events.getNextEvent(event)
                if (event.eventType == android.app.usage.UsageEvents.Event.MOVE_TO_FOREGROUND
                    && event.timeStamp > lastTs) {
                    lastTs  = event.timeStamp
                    lastPkg = event.packageName ?: ""
                }
            }

            if (lastPkg.isNotEmpty()) { promise.resolve(lastPkg); return }

            // Method 2: UsageStats fallback
            val stats = usm.queryUsageStats(
                UsageStatsManager.INTERVAL_DAILY, now - window, now
            )
            if (stats != null && stats.isNotEmpty()) {
                val sorted: SortedMap<Long, android.app.usage.UsageStats> = TreeMap()
                for (s in stats) sorted[s.lastTimeUsed] = s
                if (sorted.isNotEmpty()) {
                    promise.resolve(sorted[sorted.lastKey()]?.packageName ?: "")
                    return
                }
            }

            promise.resolve("")
        } catch (e: Exception) {
            promise.resolve("")
        }
    }

    // ── Installed apps ────────────────────────────────────────────────────────
    // Returns user-installed apps only (filters out system packages).
    // Shape: [{ appName, packageName, hint }]

    private val IGNORE_FRAGMENTS = listOf(
        "android", "com.google.android.gms", "com.android",
        "com.samsung.android.app.settings", "com.sec.android",
        "com.qualcomm", "com.mediatek"
    )

    @ReactMethod
    fun getInstalledApps(promise: Promise) {
        try {
            val pm    = reactContext.packageManager
            val flags = PackageManager.GET_META_DATA
            val apps  = pm.getInstalledApplications(flags)

            val result = WritableNativeArray()

            for (app in apps) {
                // Skip system apps
                if (app.flags and ApplicationInfo.FLAG_SYSTEM != 0) continue
                val pkg = app.packageName ?: continue
                if (IGNORE_FRAGMENTS.any { pkg.startsWith(it) }) continue

                val label = pm.getApplicationLabel(app).toString()
                if (label.isBlank()) continue

                // Instead of last segment only, use last 2 segments
                val parts = pkg.split(".")
                val hint = if (parts.size >= 2) parts.takeLast(2).joinToString(".") else pkg

                val map = WritableNativeMap()
                map.putString("appName",     label)
                map.putString("packageName", pkg)
                map.putString("hint",        hint)
                result.pushMap(map)
            }

            promise.resolve(result)
        } catch (e: Exception) {
            promise.resolve(WritableNativeArray())
        }
    }

    @ReactMethod
    fun hasOverlayPermission(promise: Promise) {
        try {
            val granted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                Settings.canDrawOverlays(reactContext)
            } else true
            promise.resolve(granted)
        } catch (e: Exception) {
            promise.resolve(false)
        }
    }
}
